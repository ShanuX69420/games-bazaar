from .development import *

# Local development overrides
# You can override any settings here for your local development environment

# Example: Enable Django Debug Toolbar in local development
try:
    import debug_toolbar
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
    INTERNAL_IPS = ['127.0.0.1']
except ImportError:
    pass

# Example: Use different database for local testing
# DATABASES['default']['NAME'] = 'test_gamers_market.db'