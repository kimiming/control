module.exports = {
  apps: [
    {
      name: 'tg-marketing-backend',
      cwd: '/var/www/tg-marketing/backend',
      script: '/var/www/tg-marketing/backend/.venv/bin/uvicorn',
      args: 'main:app --host 127.0.0.1 --port 8000 --proxy-headers',
      interpreter: 'none',
      autorestart: true,
      max_memory_restart: '512M',
      out_file: '/var/log/tg-marketing/backend.log',
      error_file: '/var/log/tg-marketing/backend-error.log',
    },
  ],
};
