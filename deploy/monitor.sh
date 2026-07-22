#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --project-directory "$PROJECT_DIR")

if [ -t 1 ]; then
  BLUE='\033[1;34m'
  GREEN='\033[1;32m'
  YELLOW='\033[1;33m'
  RESET='\033[0m'
else
  BLUE=''
  GREEN=''
  YELLOW=''
  RESET=''
fi

section() {
  printf '\n%b%s%b\n' "$BLUE" "$1" "$RESET"
  printf '%s\n' '------------------------------------------------------------'
}

human_kib() {
  awk -v kib="$1" 'BEGIN {
    split("KiB MiB GiB TiB", unit, " "); value = kib; idx = 1;
    while (value >= 1024 && idx < 4) { value /= 1024; idx++ }
    printf "%.2f %s", value, unit[idx]
  }'
}

cpu_usage() {
  local cpu user nice system idle iowait irq softirq steal guest guest_nice
  local idle_before total_before idle_after total_after
  read -r cpu user nice system idle iowait irq softirq steal guest guest_nice < /proc/stat
  idle_before=$((idle + iowait))
  total_before=$((user + nice + system + idle + iowait + irq + softirq + steal))
  sleep 1
  read -r cpu user nice system idle iowait irq softirq steal guest guest_nice < /proc/stat
  idle_after=$((idle + iowait))
  total_after=$((user + nice + system + idle + iowait + irq + softirq + steal))
  awk -v idle_delta="$((idle_after - idle_before))" -v total_delta="$((total_after - total_before))" \
    'BEGIN { if (total_delta <= 0) print "0.0"; else printf "%.1f", 100 * (total_delta - idle_delta) / total_delta }'
}

if ! command -v docker >/dev/null 2>&1; then
  printf '%b错误：未找到 Docker。%b\n' "$YELLOW" "$RESET" >&2
  exit 1
fi

if ! "${COMPOSE[@]}" config --quiet >/dev/null 2>&1; then
  printf '%b错误：无法读取 %s/docker-compose.yml。%b\n' "$YELLOW" "$PROJECT_DIR" "$RESET" >&2
  exit 1
fi

timestamp="$(date '+%Y-%m-%d %H:%M:%S %Z')"
hostname_value="$(hostname)"
cpu_cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc)"
load_average="$(awk '{print $1" / "$2" / "$3}' /proc/loadavg)"
cpu_percent="$(cpu_usage)"
read -r mem_total mem_used mem_free mem_shared mem_cache mem_available < <(free -k | awk '/^Mem:/ {print $2,$3,$4,$5,$6,$7}')
read -r swap_total swap_used swap_free < <(free -k | awk '/^Swap:/ {print $2,$3,$4}')
read -r disk_size disk_used disk_available disk_percent < <(df -kP / | awk 'NR==2 {print $2,$3,$4,$5}')
inode_percent="$(df -Pi / | awk 'NR==2 {print $5}')"

printf '%bControl 项目性能报告%b  %s  主机：%s\n' "$GREEN" "$RESET" "$timestamp" "$hostname_value"

section '一、整机资源'
printf 'CPU              : %s 核，当前使用 %s%%，空闲约 %.1f%%\n' "$cpu_cores" "$cpu_percent" "$(awk -v value="$cpu_percent" 'BEGIN { print 100-value }')"
printf '系统负载(1/5/15m): %s\n' "$load_average"
printf '内存             : 总计 %s，已用 %s，可用 %s\n' "$(human_kib "$mem_total")" "$(human_kib "$mem_used")" "$(human_kib "$mem_available")"
if [ "${swap_total:-0}" -gt 0 ]; then
  printf 'Swap             : 总计 %s，已用 %s，可用 %s\n' "$(human_kib "$swap_total")" "$(human_kib "$swap_used")" "$(human_kib "$swap_free")"
else
  printf 'Swap             : 未配置\n'
fi
printf '系统盘 /         : 总计 %s，已用 %s，剩余 %s，使用率 %s\n' "$(human_kib "$disk_size")" "$(human_kib "$disk_used")" "$(human_kib "$disk_available")" "$disk_percent"
printf 'inode 使用率     : %s\n' "$inode_percent"
printf '系统运行时间     : %s\n' "$(uptime -p 2>/dev/null || true)"

section '二、Docker 占用'
docker system df 2>/dev/null || printf '无法读取 Docker 磁盘占用。\n'
printf '\n%-32s %-9s %-24s %-7s\n' '容器' 'CPU' '内存使用 / 上限' '进程数'
docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.PIDs}}' 2>/dev/null \
  | sort \
  | awk -F'|' '{printf "%-32s %-9s %-24s %-7s\n", $1, $2, $3, $4}'

section '三、CPU 与 I/O 快照'
if command -v vmstat >/dev/null 2>&1; then
  printf '%-9s %-9s %-9s %-9s %-9s %-9s\n' '用户CPU' '系统CPU' '空闲CPU' 'I/O等待' '被偷取CPU' '运行队列'
  vmstat 1 2 | tail -1 | awk '{printf "%-9s %-9s %-9s %-9s %-9s %-9s\n", $13"%", $14"%", $15"%", $16"%", $17"%", $1}'
else
  printf 'vmstat 不可用；整机 CPU 使用率为 %s%%。\n' "$cpu_percent"
fi

section '四、当前业务量'
business_output="$("${COMPOSE[@]}" exec -T backend python -c '
from sqlalchemy import func, select
from app.core.database import SessionLocal
from app.models.customer import Customer
from app.models.material import Material
from app.models.message import Message
from app.models.session import SessionStatus, TelegramSession
from app.models.task import MarketingTask

db = SessionLocal()
try:
    values = {
        "Session总数": db.scalar(select(func.count()).select_from(TelegramSession)) or 0,
        "已连接Session": db.scalar(select(func.count()).select_from(TelegramSession).where(TelegramSession.status == SessionStatus.connected)) or 0,
        "消息总数": db.scalar(select(func.count()).select_from(Message)) or 0,
        "客户总数": db.scalar(select(func.count()).select_from(Customer)) or 0,
        "素材总数": db.scalar(select(func.count()).select_from(Material)) or 0,
        "任务总数": db.scalar(select(func.count()).select_from(MarketingTask)) or 0,
    }
    for name, value in values.items():
        print(f"{name}|{value}")
finally:
    db.close()
' 2>/dev/null)" || true

if [ -n "$business_output" ]; then
  printf '%s\n' "$business_output" | awk -F'|' '{printf "%-20s : %s\n", $1, $2}'
else
  printf '后端未运行或数据库暂时不可访问。\n'
fi

static_size="$(du -sh "$PROJECT_DIR/backend/static" 2>/dev/null | awk '{print $1}')"
redis_memory="$("${COMPOSE[@]}" exec -T redis redis-cli INFO memory 2>/dev/null | awk -F: '/^used_memory_human:/ {gsub(/\r/, "", $2); print $2}')"
printf '%-20s : %s\n' '素材文件目录' "${static_size:-未知}"
printf '%-20s : %s\n' 'Redis数据内存' "${redis_memory:-未知}"

section '五、服务状态'
"${COMPOSE[@]}" ps --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null || "${COMPOSE[@]}" ps

printf '\n报告完成。该脚本仅执行只读检查，不会修改或重启服务。\n'
