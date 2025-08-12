module.exports = {
  apps: [{
    name: 'games-bazaar',
    cwd: '/home/gamersmarket/app',
    script: '/bin/bash',
    args: ['-c', 'source /home/gamersmarket/app/venv/bin/activate && cd /home/gamersmarket/app && daphne -b 0.0.0.0 -p 8000 core.asgi:application'],
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      DJANGO_SETTINGS_MODULE: 'core.settings.production',
      PYTHONPATH: '/home/gamersmarket/app'
    },
    error_file: '/home/gamersmarket/app/logs/pm2-error.log',
    out_file: '/home/gamersmarket/app/logs/pm2-out.log',
    log_file: '/home/gamersmarket/app/logs/pm2-combined.log',
    time: true,
    merge_logs: true,
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
  }]
};