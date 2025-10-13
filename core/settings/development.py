from .base import *

# Ensure security middleware runs even in development (for lockout testing)
insert_index = 4  # After CSP middleware to keep ordering similar to production
if 'marketplace.security_middleware.SecurityMiddleware' not in MIDDLEWARE:
    MIDDLEWARE.insert(insert_index, 'marketplace.security_middleware.SecurityMiddleware')

# Development-specific settings
DEBUG = True

# Allow access from mobile devices on local network
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '192.168.100.11', '0.0.0.0']

# Enable caching for development (in-memory)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
            'CULL_FREQUENCY': 3,
        }
    }
}

# Channels for development (in-memory)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    },
}

# Development logging
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
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'marketplace': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Email backend for development
# Use console backend by default to avoid sending real emails.
# Can be overridden via EMAIL_BACKEND env var (e.g., to SMTP) if needed.
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')

# Site configuration for password reset links  
DEFAULT_FROM_EMAIL = 'no-reply@gamesbazaarpk.com'
SERVER_EMAIL = 'no-reply@gamesbazaarpk.com'
