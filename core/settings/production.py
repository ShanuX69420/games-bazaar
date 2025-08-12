from .base import *

# Production-specific settings
DEBUG = False

# Security Settings
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Security Headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Session Security
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 30 * 24 * 60 * 60  # 30 days
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Don't expire when browser closes
SESSION_SAVE_EVERY_REQUEST = True  # Extend session on every request

# Frame Options
X_FRAME_OPTIONS = 'DENY'

# Content Security Policy (basic)
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Production caching with Redis
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# Channels with Redis for production
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config('REDIS_URL', default='redis://127.0.0.1:6379/0')],
        },
    },
}

# Session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'

# Production logging with sensitive data protection
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
    'filters': {
        'sensitive_data_filter': {
            '()': 'core.logging_filters.SensitiveDataFilter',
        },
        'payment_callback_filter': {
            '()': 'core.logging_filters.PaymentCallbackFilter',
        },
        'auth_filter': {
            '()': 'core.logging_filters.AuthenticationFilter',
        },
        'request_data_filter': {
            '()': 'core.logging_filters.RequestDataFilter',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'filters': ['sensitive_data_filter'],
        },
        'security_console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['sensitive_data_filter', 'request_data_filter'],
        },
        'payment_console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'filters': ['sensitive_data_filter', 'payment_callback_filter'],
        },
        'auth_console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'filters': ['sensitive_data_filter', 'auth_filter'],
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'marketplace': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'marketplace.security': {
            'handlers': ['security_console'],
            'level': 'INFO',
            'propagate': False,
        },
        'marketplace.access': {
            'handlers': ['security_console'],
            'level': 'INFO',
            'propagate': False,
        },
        'marketplace.payment': {
            'handlers': ['payment_console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.contrib.auth': {
            'handlers': ['auth_console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Email backend for production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

# File upload security
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

# Additional security for production
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True

# Performance and reliability settings
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000
DATA_UPLOAD_MAX_NUMBER_FILES = 20

# Error handling for production
ADMINS = [
    ('Admin', config('ADMIN_EMAIL', default='admin@gamesbazaarpk.com')),
]
MANAGERS = ADMINS

# Server error logging
SERVER_EMAIL = config('SERVER_EMAIL', default='server@gamesbazaarpk.com')

# Custom error pages
CUSTOM_500_ERROR_VIEW = True

# Database backup settings
DATABASE_BACKUP_ENABLED = config('DATABASE_BACKUP_ENABLED', default=True, cast=bool)
DATABASE_BACKUP_SCHEDULE = config('DATABASE_BACKUP_SCHEDULE', default='daily')

# Add security middleware
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'marketplace.security_middleware.SecurityMiddleware',  # Custom security middleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'marketplace.middleware.UpdateLastSeenMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]