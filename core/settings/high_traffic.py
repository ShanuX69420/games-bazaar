from .production import *

# High Traffic Production Settings
# For handling 10,000+ concurrent users

# Database Configuration with Connection Pooling
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
        'OPTIONS': {
            'MAX_CONNS': 20,  # Connection pooling
            'MIN_CONNS': 5,
        },
        'CONN_MAX_AGE': 600,  # Keep connections alive for 10 minutes
    }
}

# Redis Configuration with Clustering
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': [
            config('REDIS_URL_1', default='redis://127.0.0.1:6379/1'),
            config('REDIS_URL_2', default='redis://127.0.0.1:6380/1'),
            config('REDIS_URL_3', default='redis://127.0.0.1:6381/1'),
        ],
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.ShardClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 50,
                'retry_on_timeout': True,
            }
        }
    }
}

# Session Configuration for High Traffic
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 30 * 24 * 60 * 60  # 30 days
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Don't expire when browser closes  
SESSION_SAVE_EVERY_REQUEST = True  # Extend session on every request

# Channels Configuration for WebSocket Scaling
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                config('REDIS_URL_1', default='redis://127.0.0.1:6379/0'),
                config('REDIS_URL_2', default='redis://127.0.0.1:6380/0'),
            ],
            "capacity": 1500,  # Increased capacity
            "expiry": 60,      # Message expiry
        },
    },
}

# File Upload Limits for High Traffic
FILE_UPLOAD_MAX_MEMORY_SIZE = 2621440   # 2.5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 2621440   # 2.5MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Security Settings for High Traffic
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Logging for High Traffic
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'verbose',
            'maxBytes': 1024*1024*50,  # 50MB
            'backupCount': 5,
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'error.log',
            'formatter': 'verbose',
            'maxBytes': 1024*1024*50,  # 50MB
            'backupCount': 5,
        },
        'console': {
            'level': 'ERROR',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['error_file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'marketplace': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Email Backend for High Volume
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_TIMEOUT = 10  # Reduced timeout for high traffic