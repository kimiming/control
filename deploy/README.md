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
cp backend/.env.example backend/.env
vim backend/.env
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
cp backend/.env.example backend/.env
docker compose up -d --build
```
