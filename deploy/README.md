# 部署说明

## Ubuntu 22.04 裸机部署

1. 安装依赖：

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nodejs npm nginx mysql-server redis-server certbot python3-certbot-nginx rsync
```

2. 初始化数据库：

```bash
sudo mysql < deploy/mysql/init.sql
```

3. 配置环境变量：

```bash
cp .env.example .env
cp backend/.env.example backend/.env
vim .env
vim backend/.env
```

在根目录 `.env` 中设置本机需要启动的 session worker 数量（支持 1-12）：

```dotenv
SESSION_WORKER_COUNT=6
```

4. 修改 `deploy/nginx/tg-marketing.conf` 中的 `server_name` 和证书路径。

5. 执行部署：

```bash
chmod +x deploy/deploy.sh
APP_DIR=/var/www/tg-marketing ./deploy/deploy.sh
```

6. 申请 SSL：

```bash
sudo certbot --nginx -d example.com
```

## Docker Compose 部署

```bash
cp .env.example .env
cp backend/.env.example backend/.env
vim .env
./deploy/compose-up.sh
```

每台服务器的 `.env` 都不会提交到 Git，因此可以使用不同的
`SESSION_WORKER_COUNT`。以后拉取代码后再次执行 `./deploy/compose-up.sh` 即可；
脚本会启动指定数量的 worker，并停止超出数量的旧 worker。
