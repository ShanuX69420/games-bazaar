import os
from pathlib import Path
from decouple import config, Csv
import dj_database_url

"""
Base Django settings for core project.
"""

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

# Admin URL configuration (strip leading slashes and enforce trailing slash)
ADMIN_URL = config('ADMIN_URL', default='secure-admin/')
ADMIN_URL = ADMIN_URL.lstrip('/')
if not ADMIN_URL.endswith('/'):
    ADMIN_URL = f'{ADMIN_URL}/'

# Admin rate limit whitelist (comma-separated IPs)
ADMIN_RATE_LIMIT_WHITELIST = [
    value for value in config('ADMIN_RATE_LIMIT_WHITELIST', default='', cast=Csv())
    if value
]

# CSRF Protection Configuration
CSRF_TRUSTED_ORIGINS = [
    'https://gamesbazaarpk.com',
    'https://www.gamesbazaarpk.com',
    'https://gamesbazaar.pk',
    'https://www.gamesbazaar.pk',
]

# Application definition
INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'marketplace.apps.MarketplaceConfig',
    'channels',
    'model_utils',
    'django.contrib.sites', # Required by allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.facebook',
]

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'core.middleware.CSPMiddleware',
    'django_permissions_policy.PermissionsPolicyMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'marketplace.middleware.UpdateLastSeenMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'marketplace.context_processors.notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

# Database with enhanced configuration for performance and security
# Production safety: Never allow SQLite fallback in production
if not DEBUG:
    # In production, DATABASE_URL must be explicitly set to a PostgreSQL database
    DATABASE_URL = config('DATABASE_URL')  # Will raise ImproperlyConfigured if missing
    if not DATABASE_URL.startswith(('postgres://', 'postgresql://')):
        raise Exception("Production requires PostgreSQL database. SQLite is not allowed in production.")
else:
    # Development fallback to SQLite is allowed
    DATABASE_URL = config('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')

DATABASES = {
    'default': dj_database_url.parse(DATABASE_URL)
}

# Enhanced database configuration for production
if 'postgresql' in DATABASES['default']['ENGINE']:
    DATABASES['default'].update({
        'CONN_MAX_AGE': 600,  # Keep connections alive for 10 minutes
        'OPTIONS': {
            'connect_timeout': 10,
        }
    })

# Database query optimization settings
DATABASE_QUERY_TIMEOUT = 30  # 30 seconds timeout for slow queries

# Enhanced password validation for better security
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        'OPTIONS': {
            'user_attributes': ['username', 'email', 'first_name', 'last_name'],
            'max_similarity': 0.7,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 12,  # Require longer passwords for privileged users
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Additional security settings for authentication
LOGIN_ATTEMPTS_LIMIT = 5
LOGIN_ATTEMPTS_TIMEOUT = 300  # 5 minutes lockout

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# Media files
# Allow override via env (e.g., CDN/GCS domain in production)
MEDIA_URL = config('MEDIA_URL', default='/media/')
MEDIA_ROOT = BASE_DIR / 'media'

# Google Cloud Storage Configuration
GS_BUCKET_NAME = config('GS_BUCKET_NAME', default='')
GS_PROJECT_ID = config('GS_PROJECT_ID', default='')
GS_CREDENTIALS = config('GOOGLE_APPLICATION_CREDENTIALS', default='')
GS_CUSTOM_ENDPOINT = config('GS_CUSTOM_ENDPOINT', default='')  # Your custom DNS domain
GS_DEFAULT_ACL = 'publicRead'
GS_FILE_OVERWRITE = False
GS_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB

# Set the Google Application Credentials environment variable
import os
if GS_CREDENTIALS and os.path.exists(GS_CREDENTIALS):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GS_CREDENTIALS

# Enable Google Cloud Storage for new images only
USE_GCS_FOR_NEW_IMAGES = config('USE_GCS_FOR_NEW_IMAGES', default=False, cast=bool)

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication
LOGIN_REDIRECT_URL = '/'
LOGIN_URL = 'login'
LOGOUT_REDIRECT_URL = '/'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

# Social Account Settings
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    },
    'facebook': {
        'METHOD': 'oauth2',
        'SDK_URL': '//connect.facebook.net/{locale}/sdk.js',
        'SCOPE': ['email', 'public_profile'],
        'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
        'INIT_PARAMS': {'cookie': True},
        'FIELDS': [
            'id',
            'email',
            'name',
            'first_name',
            'last_name',
            'verified',
            'locale',
            'timezone',
            'link',
            'gender',
            'updated_time',
        ],
        'EXCHANGE_TOKEN': True,
        'LOCALE_FUNC': lambda request: 'en_US',
        'VERIFIED_EMAIL': False,
        'VERSION': 'v13.0',
    }
}

# reCAPTCHA Settings (using environment variables for security)
RECAPTCHA_PUBLIC_KEY = config('RECAPTCHA_PUBLIC_KEY', default='')
RECAPTCHA_PRIVATE_KEY = config('RECAPTCHA_PRIVATE_KEY', default='')

# Email Configuration (using environment variables for security)
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='smtp-relay.brevo.com')
EMAIL_PORT = config('EMAIL_PORT', default=2525, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')

# WhiteNoise settings (consolidated)
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_SKIP_COMPRESS_EXTENSIONS = []
WHITENOISE_MAX_AGE = 31536000
# Allauth Settings
ACCOUNT_EMAIL_VERIFICATION = 'optional'
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
DEFAULT_FROM_EMAIL = 'no-reply@gamesbazaar.pk'
SERVER_EMAIL = 'no-reply@gamesbazaar.pk'

# Manual wallet top-up bank details (override via environment variables in production)
MANUAL_DEPOSIT_DETAILS = {
    'bank_name': config('DEPOSIT_BANK_NAME', default='Update bank name'),
    'account_title': config('DEPOSIT_ACCOUNT_TITLE', default='Update account title'),
    'account_number': config('DEPOSIT_ACCOUNT_NUMBER', default='Update account number'),
    'iban': config('DEPOSIT_IBAN', default='Update IBAN'),
    'branch': config('DEPOSIT_BRANCH', default=''),
}

# Security Headers Configuration
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# SSL/HTTPS Security (enable in production)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Cookie SameSite settings for enhanced security
SESSION_COOKIE_SAMESITE = 'Lax'  # Allows navigation from external sites
CSRF_COOKIE_SAMESITE = 'Lax'     # Required for CSRF protection to work with forms
SESSION_COOKIE_HTTPONLY = True   # Prevent XSS access to session cookies

# Share cookies between domain and subdomain (override in dev to allow localhost)
if DEBUG:
    SESSION_COOKIE_DOMAIN = None
    CSRF_COOKIE_DOMAIN = None
else:
    SESSION_COOKIE_DOMAIN = config('SESSION_COOKIE_DOMAIN', default='.gamesbazaar.pk')
    CSRF_COOKIE_DOMAIN = config('CSRF_COOKIE_DOMAIN', default='.gamesbazaar.pk')

# Content Security Policy
CSP_DEFAULT_SRC = ["'self'"]
CSP_SCRIPT_SRC = [
    "'self'",
    "'nonce-{nonce}'",
    "https://apis.google.com",
    "https://connect.facebook.net",
    "https://www.google.com/recaptcha/",
    "https://www.gstatic.com/recaptcha/",
    "https://js.stripe.com",
    "https://cdn.jsdelivr.net",
]
CSP_STYLE_SRC = [
    "'self'",
    "'unsafe-inline'",  # Keep inline styles allowed for now to avoid breakage
    "https://fonts.googleapis.com",
    "https://cdnjs.cloudflare.com",
    "https://cdn.jsdelivr.net",
]
CSP_FONT_SRC = [
    "'self'",
    "https://fonts.gstatic.com",
    "https://cdnjs.cloudflare.com",
    "https://cdn.jsdelivr.net",
]
CSP_IMG_SRC = [
    "'self'",
    "data:",
    "https:",
    "blob:",
]
CSP_CONNECT_SRC = [
    "'self'",
    "https://api.stripe.com",
    "https://www.google-analytics.com",
    "wss:",
    "ws:",
]
CSP_FRAME_SRC = [
    "https://www.google.com/recaptcha/",
    "https://recaptcha.google.com/recaptcha/",
    "https://js.stripe.com",
    "https://www.facebook.com",
    "https://accounts.google.com",
]

# Additional Security Headers
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
PERMISSIONS_POLICY = {
    "accelerometer": [],
    "autoplay": [],
    "camera": [],
    "display-capture": [],
    "encrypted-media": [],
    "fullscreen": [],
    "geolocation": [],
    "gyroscope": [],
    "magnetometer": [],
    "microphone": [],
    "midi": [],
    "payment": [],
    "picture-in-picture": [],
    "publickey-credentials-get": [],
    "screen-wake-lock": [],
    "sync-xhr": [],
    "usb": [],
    "web-share": [],
    "xr-spatial-tracking": [],
}
