from .base import *

# Development-specific settings
DEBUG = True

# Remove Daphne to use Django's built-in server
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'daphne']

# Basic development caching
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

# Remove ASGI application for simple HTTP server
# ASGI_APPLICATION = None

# Simple logging for development
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable channels for simple development
CHANNEL_LAYERS = {}