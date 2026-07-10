# TG 运营管理控制台

一个基于 FastAPI、React、MySQL、Redis、Telethon 的 Telegram Session 运营管理系统。项目支持 Session 批量导入、分组、代理分配、任务群发、素材库、客户资料、客服消息工作台、用户登录和数据隔离。

## 功能概览

- 登录与权限
  - 默认 root 用户：`root / root`
  - 默认普通用户：`test / test`
  - root 可以创建和编辑普通用户。
  - 普通用户只能看到自己独立的一份业务数据。
- Session 管理
  - 批量导入 `.session` 文件。
  - 批量连接、批量删除、健康检查。
  - 分组、客服、代理绑定。
  - 显示连接状态、健康状态、头像、用户名、已发送数量、任务日志。
- 代理管理
  - 支持 HTTP / HTTPS / SOCKS4 / SOCKS5。
  - 支持按 Session 分组绑定代理。
  - 支持启用、测试、Tag 颜色。
- 素材库管理
  - 文字素材、图片素材、TG 名片素材。
  - 图片会在后端压缩保存，避免长期占用太多磁盘。
- 任务管理
  - 支持文字、图片、名片发送。
  - 支持手动导入 TXT 或选择客户资料。
  - 支持任务进度、执行状态、防重复点击执行。
- 消息列表
  - 客服工作台式聊天界面。
  - 支持文字回复。
  - 支持通过素材库发送文字、图片、名片。
  - 打开会话和回复前会向 Telegram 发送已读回执。

## 技术栈

- 后端：Python 3.12、FastAPI、SQLAlchemy、Telethon
- 前端：React 18、Vite、Ant Design、React Query
- 数据库：MySQL 8
- 缓存/队列：Redis 7
- 部署：Docker Compose、Nginx

## 目录结构

```text
.
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/             # API 路由
│   │   ├── core/            # 配置、数据库、认证、迁移
│   │   ├── models/          # SQLAlchemy 模型
│   │   └── services/        # 业务服务
│   ├── static/              # 运行时静态文件，上传图片/头像
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/                # React 前端
│   ├── src/
│   ├── Dockerfile
│   └── nginx.frontend.conf
├── deploy/
│   ├── deploy.sh            # Ubuntu Docker 一键部署脚本
│   └── mysql/init.sql       # MySQL 初始化脚本
├── docker-compose.yml
└── README.md
```

## 快速部署

在 Ubuntu 服务器上执行：

```bash
git clone <你的仓库地址> control
cd control
bash deploy/deploy.sh
```

部署完成后访问：

```text
http://服务器IP:8080/login
```

默认账号：

```text
root / root
test / test
```

首次部署后建议立即登录 root 修改用户密码。

## 环境配置

后端配置文件位于：

```text
backend/.env
```

如果不存在，部署脚本会从 `backend/.env.example` 自动复制。

关键配置：

```env
APP_NAME=TG Marketing System
API_PREFIX=/api
DATABASE_URL=mysql+pymysql://tg_user:change_me@mysql:3306/tg_marketing?charset=utf8mb4
REDIS_URL=redis://redis:6379/0
TELEGRAM_API_ID=2040
TELEGRAM_API_HASH=你的_API_HASH
TELEGRAM_PROXY_URL=
AUTH_SECRET=请改成随机长字符串
SESSION_DIR=/app/telegram_sessions
CORS_ORIGINS=["http://localhost:8080","http://127.0.0.1:8080"]
```

## 常用运维命令

启动或更新：

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

查看后端日志：

```bash
docker compose logs -f backend
```

查看前端日志：

```bash
docker compose logs -f frontend
```

停止服务：

```bash
docker compose down
```

备份 MySQL：

```bash
docker compose exec mysql mysqldump -utg_user -pchange_me tg_marketing > backup.sql
```

## 数据与文件持久化

Docker Compose 默认使用这些持久化位置：

- `mysql_data`：MySQL 数据卷
- `redis_data`：Redis 数据卷
- `telegram_sessions`：Telegram `.session` 文件数据卷
- `./backend/static`：素材图片、头像、任务图片

`backend/static` 和 `.session` 文件不应提交到 Git。

## 安全说明

- `.env` 不能提交到远程仓库。
- 默认账号只适合首次部署，正式使用应马上修改密码。
- `AUTH_SECRET` 必须改成随机长字符串。
- Telegram API_ID/API_HASH 属于敏感配置，不建议写进公开仓库。
- 建议服务器防火墙只开放必要端口，例如 `22` 和 `8080`。

## 开发模式

后端本地开发：

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

前端本地开发：

```bash
cd frontend
npm install
npm run dev
```

## API 文档

后端启动后访问：

```text
http://127.0.0.1:8000/docs
```
