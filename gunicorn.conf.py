# Gunicorn configuration file for Games Bazaar

# Server socket
bind = "0.0.0.0:8080"
backlog = 2048

# Worker processes
workers = 2  # 2 workers for 1GB RAM (rule of thumb: 2 * CPU cores)
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
errorlog = "/home/gamersmarket/app/logs/gunicorn-error.log"
accesslog = "/home/gamersmarket/app/logs/gunicorn-access.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'games-bazaar-gunicorn'

# Daemon mode
daemon = False  # PM2 will manage the process

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Performance
preload_app = True
sendfile = True

# Process monitoring
pidfile = "/home/gamersmarket/app/logs/gunicorn.pid"