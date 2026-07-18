#!/usr/bin/env bash
set -euo pipefail

proxy_url="${1:-http://192.168.1.20:10808}"
dropin_dir=/etc/systemd/system/docker.service.d
dropin_file="$dropin_dir/http-proxy.conf"
daemon_config=/etc/docker/daemon.json

if [[ $EUID -ne 0 ]]; then
  echo "请使用 sudo 运行此脚本" >&2
  exit 1
fi

install -d -m 0755 "$dropin_dir"

tmp_file=$(mktemp)
trap 'rm -f "$tmp_file"' EXIT

printf '%s\n' \
  '[Service]' \
  "Environment=\"HTTP_PROXY=$proxy_url\"" \
  "Environment=\"HTTPS_PROXY=$proxy_url\"" \
  'Environment="NO_PROXY=localhost,127.0.0.1,::1,mysql,redis,tg-marketing-mysql,tg-marketing-redis"' \
  > "$tmp_file"

install -m 0644 "$tmp_file" "$dropin_file"

# BuildKit image metadata requests may bypass the daemon's systemd proxy.
# Registry mirrors avoid the Docker Hub authentication endpoint entirely.
python3 - "$daemon_config" <<'PY'
import json
import os
import sys

path = sys.argv[1]
config = {}
if os.path.exists(path):
    with open(path, encoding="utf-8") as handle:
        config = json.load(handle)

config["registry-mirrors"] = [
    "https://docker.xuanyuan.me",
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io",
]

tmp_path = path + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as handle:
    json.dump(config, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
os.chmod(tmp_path, 0o644)
os.replace(tmp_path, path)
PY

systemctl daemon-reload
systemctl restart docker

echo "Docker daemon 代理已设置为 $proxy_url"
systemctl show --property=Environment docker
echo "Docker registry mirrors 已配置："
docker info --format '{{json .RegistryConfig.Mirrors}}'
