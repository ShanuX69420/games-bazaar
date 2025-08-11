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

# Logging - Secure configuration to prevent sensitive data exposure
errorlog = "/var/log/gunicorn/gunicorn-error.log"
accesslog = "/var/log/gunicorn/gunicorn-access.log"
loglevel = "warning"  # Changed from 'info' to 'warning' to reduce log verbosity
# Custom access log format that excludes sensitive query parameters and headers
# %(h)s = client IP, %(t)s = timestamp, %(m)s = method, %(U)s = URL path (no query string), 
# %(s)s = status, %(b)s = response size, %(D)s = request time
access_log_format = '%(h)s - - [%(t)s] "%(m)s %(U)s HTTP/1.1" %(s)s %(b)s %(D)s'

# Log filtering function to prevent sensitive data in logs
def on_starting(server):
    """Called just before the master process is initialized."""
    import logging
    import re
    
    class SensitiveDataFilter(logging.Filter):
        """Filter to remove sensitive data from log records."""
        
        def __init__(self):
            super().__init__()
            # Patterns to identify sensitive data
            self.sensitive_patterns = [
                r'password[=:]\w+',
                r'token[=:]\w+', 
                r'key[=:]\w+',
                r'session[=:]\w+',
                r'authorization:\s*\w+',
                r'cookie:\s*[^;]+',
                r'csrftoken[=:]\w+',
                r'sessionid[=:]\w+'
            ]
            self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.sensitive_patterns]
        
        def filter(self, record):
            if hasattr(record, 'getMessage'):
                message = record.getMessage()
                for pattern in self.compiled_patterns:
                    message = pattern.sub('[FILTERED]', message)
                record.msg = message
            return True
    
    # Apply filter to gunicorn loggers
    for logger_name in ['gunicorn.error', 'gunicorn.access']:
        logger = logging.getLogger(logger_name)
        logger.addFilter(SensitiveDataFilter())

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
pidfile = "/var/run/gunicorn/gunicorn.pid"