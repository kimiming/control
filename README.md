# TG 运营管理控制台

一个基于 FastAPI、React、MySQL、Redis、Telethon 的 Telegram Session 运营管理系统。它把 Session、代理、素材、客户资料、群发任务和客服回复整合到一个控制台里，适合需要批量维护 Telegram 账号和消息任务的场景。

## 项目能做什么

- 控制面板
  - 汇总 Session、消息、素材、客户资料和任务核心指标。
  - 使用 ECharts 展示状态分布、7 日趋势、分组规模和任务发送质量。
- Session 管理
  - 导入 `.session` 文件，或导入账号清单。
  - 将全部或勾选的 `.session` 文件打包导出备份。
  - 分组、绑定代理、绑定客服。
  - 批量连接、断开、健康检查、双向检测。
  - 扫描、导入、清空 Telegram 联系人。
- 客户与消息
  - 保存会话消息。
  - 客服工作台式查看客户会话。
  - 支持文字回复，或通过素材库发送文字、图片、名片。
  - 打开会话和回复时会发送已读回执。
- 素材与任务
  - 维护文字、图片、TG 名片素材。
  - 支持素材分组和批量导入。
  - 支持按手机号或用户名批量发送任务。
  - 支持暂停、继续、取消、重试未发送目标。
- 权限与隔离
  - 内置 `root` 管理员和普通用户。
  - 普通用户只能看到自己的数据。

## 技术栈

- 后端：FastAPI、SQLAlchemy、Telethon、Redis
- 前端：React 18、Vite、Ant Design、TanStack Query、ECharts
- 数据库：MySQL 8
- 部署：Docker Compose、Nginx

## 目录结构

```text
.
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/             # API 路由
│   │   ├── core/            # 配置、数据库、认证、轻量迁移
│   │   ├── models/          # SQLAlchemy 模型
│   │   ├── schemas/         # 请求参数定义
│   │   └── services/        # 业务逻辑
│   ├── static/              # 运行时静态文件，素材图/头像/任务图
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                # React 前端
│   ├── src/
│   ├── Dockerfile
│   └── nginx.frontend.conf
├── deploy/                  # 部署脚本和示例配置
├── docker-compose.yml
└── README.md
```

## 快速开始

推荐直接使用 Docker Compose。这是当前仓库最完整、最贴近生产的启动方式。

### 1. 准备配置

```bash
cp backend/.env.example backend/.env
```

至少修改这些配置：

```env
TELEGRAM_API_ID=你的_api_id
TELEGRAM_API_HASH=你的_api_hash
AUTH_SECRET=改成随机长字符串
```

说明：

- `TELEGRAM_API_ID` 和 `TELEGRAM_API_HASH` 需要去 `https://my.telegram.org/apps` 申请。
- `backend/.env.example` 默认数据库地址指向 Compose 容器名，适合 Docker Compose 运行。
- 默认开放端口：
  - 前端 `8080`
  - 后端 `8000`
  - MySQL `3306`
  - Redis `6379`

### 2. 启动服务

```bash
docker compose up -d --build
```

启动完成后访问：

```text
http://127.0.0.1:8080/login
```

首次会自动创建默认账号：

```text
root / root
test / test
```

建议首次登录后立刻修改密码，尤其是 `root` 账号。

### 3. 检查服务

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

健康检查地址：

- 前端：`http://127.0.0.1:8080`
- 后端：`http://127.0.0.1:8000/health`
- Swagger：`http://127.0.0.1:8000/docs`

## 一键部署

Ubuntu/Linux 服务器可以直接执行：

```bash
bash deploy/deploy.sh
```

脚本会：

- 检查并安装 Docker
- 在缺少 `backend/.env` 时从示例文件复制
- 构建并启动所有容器

部署完成后默认入口仍然是：

```text
http://服务器IP:8080/login
```

## 怎么使用这个项目

下面是按实际业务顺序整理的一套推荐使用流程。

### 1. 登录并初始化账号

- 用 `root / root` 登录后台。
- 进入“用户管理”创建业务账号。
- 业务账号登录后会拥有自己独立的数据空间。

### 2. 先建基础资源

建议先准备这几类基础数据：

- Session 分组：给不同业务线、地区或用途分组。
- 客服账号：把 Session 绑定到客服，方便后续在“客服管理”里收发消息。
- 代理：支持 `http`、`https`、`socks4`、`socks5`，可绑定到多个分组。
- 素材分组：把常用话术、图片、名片归档。

### 3. 导入 Session

系统支持两种常见方式：

- 直接导入 `.session` 文件。
  - 适合已有 Telegram 会话文件。
  - 文件名会被用作 `session_name`。
- 导入账号清单文件。
  - 支持 `txt`、`csv`、`xlsx`。
  - 支持表头字段：`phone`、`username`、`avatar`、`group_id`。
  - 也兼容中文表头，如 `手机号`、`用户名`、`头像`、`分组`。

示例 `csv/xlsx`：

```text
phone,username,avatar,group_id
+1234567890,session_a,,1
+1987654321,session_b,,1
```

示例 `txt`：

```text
+1234567890 session_a
+1987654321 session_b
```

导入后建议立刻做三件事：

- 批量绑定分组
- 批量绑定代理
- 批量执行连接或健康检查

### 4. 管理联系人

Session 页面支持联系人相关操作：

- 扫描账号当前联系人
- 导入联系人手机号 TXT
- 清空联系人

联系人导入规则：

- 只接受 TXT 内容解析
- 单次文件最大 5MB
- 单次最多导入 10000 个手机号

### 5. 准备客户资料

“客户资料管理”用于存储任务目标清单，支持两类目标：

- `phone`：手机号
- `username`：Telegram 用户名，支持 `@username` 或 `https://t.me/username`

建议把长期复用的客户池保存成客户资料，而不是每次都临时上传 TXT。

### 6. 维护素材库

素材库支持三类素材：

- `text`：文字
- `image`：图片
- `contact`：TG 名片

说明：

- 图片会压缩后保存在 `backend/static/` 下。
- 任务发送和客服回复都可以复用素材库内容。

### 7. 创建任务

任务管理支持以下关键维度：

- 目标来源
  - 上传 TXT
  - 选择客户资料
  - 使用 Session 已导入联系人
- 目标类型
  - 手机号
  - 用户名
- 发送方式
  - `single`
  - `group`
  - `concat`
- 内容组合
  - 纯文字
  - 图片
  - 名片
  - 素材库组合

推荐顺序：

1. 先确认可用 Session 已连接。
2. 先确认代理可用。
3. 先用少量目标测试。
4. 再扩大任务规模。

任务目标 TXT 示例：

```text
+1234567890
+1987654321
```

用户名目标 TXT 示例：

```text
@alice_demo
https://t.me/bob_demo
```

### 8. 在客服管理中回复客户

“客服管理”页面可以：

- 分页查看客户会话
- 按客服、关键字、回复状态、收藏状态筛选
- 发送文字回复
- 发送素材库中的文字、图片、名片

如果某个 Session 已绑定客服，收到的新消息会更方便在这个页面集中处理。

## 开发模式

### 方式一：前后端都用 Docker Compose

这是最省事的方式：

```bash
docker compose up -d --build
```

### 方式二：本地开发前后端，数据库和 Redis 走 Docker

先启动基础设施：

```bash
docker compose up -d mysql redis
```

然后复制配置文件并按本机环境改值：

```bash
cp backend/.env.example backend/.env
```

本地开发至少要把下面几项改成宿主机可访问的地址：

```env
DATABASE_URL=mysql+pymysql://tg_user:change_me@127.0.0.1:3306/tg_marketing?charset=utf8mb4
REDIS_URL=redis://127.0.0.1:6379/0
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

启动后端：

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

启动前端：

```bash
cd frontend
npm install
npm run dev
```

开发环境地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

说明：

- 前端 Vite 已经把 `/api` 和 `/ws` 代理到 `127.0.0.1:8000`。
- 如果直接使用 `backend/.env.example` 而不修改 `DATABASE_URL`，本地裸跑后端会连不上数据库，因为默认主机名是 Compose 容器名。

## 常用运维命令

启动或重建：

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f mysql
docker compose logs -f redis
```

停止服务：

```bash
docker compose down
```

停止并删除数据卷：

```bash
docker compose down -v
```

备份 MySQL：

```bash
docker compose exec mysql mysqldump -utg_user -pchange_me tg_marketing > backup.sql
```

## 数据持久化

Compose 默认会持久化这些数据：

- `control_mysql_data`：MySQL 数据
- `tg_marketing_redis_data`：Redis 数据
- `control_telegram_sessions`：Telegram `.session` 文件
- `./backend/static`：头像、素材图、任务图片

这些目录和文件建议不要提交到 Git：

- `backend/.env`
- `backend/static/*`
- Telegram `.session` 运行数据

## 配置说明

后端主要环境变量在 `backend/.env`：

```env
APP_NAME=TG Marketing System
API_PREFIX=/api
DATABASE_URL=mysql+pymysql://tg_user:change_me@tg-marketing-mysql:3306/tg_marketing?charset=utf8mb4
REDIS_URL=redis://redis:6379/0
FRONTEND_PORT=8080
BACKEND_PORT=8000
TELEGRAM_API_ID=0
TELEGRAM_API_HASH=change_me
TELEGRAM_PROXY_URL=
AUTH_SECRET=change_this_to_a_random_long_string
SESSION_DIR=/app/telegram_sessions
CORS_ORIGINS=["http://localhost:8080","http://127.0.0.1:8080"]
HEALTH_CHECK_INTERVAL_SECONDS=60
TASK_GLOBAL_CONCURRENCY=20
TASK_SESSION_LOCK_SECONDS=300
SESSION_MAX_ACTIVE_CLIENTS=200
```

重点说明：

- `TELEGRAM_PROXY_URL` 是全局兜底代理，通常留空，优先在页面里按业务配置代理。
- `TASK_GLOBAL_CONCURRENCY` 控制全局任务并发。
- `SESSION_MAX_ACTIVE_CLIENTS` 控制后台长期维持的 Telegram 客户端数量上限。

## 安全建议

- 不要把 `backend/.env` 提交到远程仓库。
- 生产环境必须修改默认账号密码。
- `AUTH_SECRET` 必须替换成随机长字符串。
- 建议限制公网暴露端口，至少不要直接暴露 MySQL 和 Redis。
- Telegram API 凭据属于敏感信息，不要写进公开仓库。

## 已知适用场景与限制

- 项目依赖 Telethon 和真实 Telegram Session，使用前需要准备合法可用的账号环境。
- 批量消息、联系人导入、代理质量都会直接影响任务成功率。
- 当前最稳妥的运行方式是 Docker Compose；裸机部署也有示例，但维护成本更高。

## 相关文档

- [deploy/README.md](/home/kimi/control/deploy/README.md)
- [docs/technical-requirements.md](/home/kimi/control/docs/technical-requirements.md)
- [docs/code-review.md](/home/kimi/control/docs/code-review.md)
