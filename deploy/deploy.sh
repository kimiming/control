#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/var/www/tg-marketing}
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)

sudo mkdir -p "$APP_DIR" /var/log/tg-marketing
sudo rsync -a --delete "$REPO_DIR/" "$APP_DIR/"
sudo chown -R www-data:www-data "$APP_DIR" /var/log/tg-marketing

cd "$APP_DIR/backend"
sudo -u www-data python3 -m venv .venv
sudo -u www-data .venv/bin/pip install --upgrade pip
sudo -u www-data .venv/bin/pip install -r requirements.txt pymysql cryptography

cd "$APP_DIR/frontend"
npm install
npm run build

sudo cp "$APP_DIR/deploy/nginx/tg-marketing.conf" /etc/nginx/sites-available/tg-marketing.conf
sudo ln -sf /etc/nginx/sites-available/tg-marketing.conf /etc/nginx/sites-enabled/tg-marketing.conf
sudo nginx -t
sudo systemctl reload nginx

sudo cp "$APP_DIR/deploy/systemd/tg-marketing-backend.service" /etc/systemd/system/tg-marketing-backend.service
sudo systemctl daemon-reload
sudo systemctl enable tg-marketing-backend
sudo systemctl restart tg-marketing-backend
sudo systemctl status tg-marketing-backend --no-pager
