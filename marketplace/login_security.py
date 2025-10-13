import json
import logging
from django.conf import settings
from django.contrib.auth.signals import user_login_failed, user_logged_in
from django.core.cache import cache
from django.dispatch import receiver


logger = logging.getLogger('marketplace.security')

ATTEMPT_LIMIT = max(getattr(settings, 'LOGIN_ATTEMPTS_LIMIT', 5), 1)
LOCKOUT_SECONDS = max(getattr(settings, 'LOGIN_ATTEMPTS_TIMEOUT', 300), 60)
LOCK_MESSAGE = (
    "Too many failed login attempts. Please try again in "
    f"{max(1, LOCKOUT_SECONDS // 60)} minute(s)."
)


def normalize_identifier(value):
    """Normalize usernames or IP addresses for consistent cache keys."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized = value.strip().lower()
    if normalized in ("", "unknown", "none"):
        return None
    return normalized


def _client_ip(request):
    """Extract the originating IP address from the request."""
    if request is None:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _attempt_key(kind, identifier):
    return f'login_attempts:{kind}:{identifier}'


def _lock_key(kind, identifier):
    return f'login_lock:{kind}:{identifier}'


def _register_failure(kind, identifier):
    """Increment counters and lock when limit is reached."""
    attempts_key = _attempt_key(kind, identifier)
    attempts = cache.get(attempts_key, 0) + 1
    cache.set(attempts_key, attempts, LOCKOUT_SECONDS)

    if attempts >= ATTEMPT_LIMIT:
        cache.set(_lock_key(kind, identifier), True, LOCKOUT_SECONDS)
        return True, attempts
    return False, attempts


def _clear_records(kind, identifier):
    """Remove attempt and lock records after successful login."""
    cache.delete(_attempt_key(kind, identifier))
    cache.delete(_lock_key(kind, identifier))


def _is_locked(kind, identifier):
    if not identifier:
        return False
    return cache.get(_lock_key(kind, identifier)) is not None


def _lock_remaining_seconds(kind, identifier):
    key = _lock_key(kind, identifier)
    if not cache.get(key):
        return None
    ttl_method = getattr(cache, 'ttl', None)
    if callable(ttl_method):
        try:
            ttl = ttl_method(key)
            if ttl is not None and ttl >= 0:
                return ttl
        except Exception:
            return None
    return None


def is_ip_locked(ip_address):
    """Check whether the IP address is currently locked out."""
    return _is_locked('ip', ip_address)


def is_user_locked(username):
    """Check whether the username is currently locked out."""
    return _is_locked('user', username)


def lockout_remaining_seconds(ip_address=None, username=None):
    """Return lockout TTL (seconds) for IP or username if available."""
    ip_ttl = _lock_remaining_seconds('ip', ip_address) if ip_address else None
    user_ttl = _lock_remaining_seconds('user', username) if username else None
    ttl_values = [ttl for ttl in (ip_ttl, user_ttl) if ttl is not None]
    if ttl_values:
        return min(ttl_values)
    return None


@receiver(user_login_failed)
def capture_failed_login(sender, credentials, request, **kwargs):
    """Track failed logins and trigger lockout when necessary."""
    credentials = credentials or {}
    ip_identifier = normalize_identifier(_client_ip(request))
    username_identifier = normalize_identifier(
        credentials.get('username')
        or credentials.get('login')
        or credentials.get('email')
    )

    lock_triggered = False
    attempt_records = []

    if ip_identifier:
        locked, attempts = _register_failure('ip', ip_identifier)
        attempt_records.append({'type': 'ip', 'value': ip_identifier, 'attempts': attempts})
        lock_triggered = lock_triggered or locked

    if username_identifier:
        locked, attempts = _register_failure('user', username_identifier)
        attempt_records.append({'type': 'user', 'value': username_identifier, 'attempts': attempts})
        lock_triggered = lock_triggered or locked

    if lock_triggered:
        logger.warning(json.dumps({
            'event_type': 'login_lockout',
            'ip': ip_identifier,
            'username': username_identifier,
            'attempt_limit': ATTEMPT_LIMIT,
            'attempts': attempt_records,
        }))


@receiver(user_logged_in)
def reset_login_records(sender, user, request, **kwargs):
    """Clear any stored counters after a successful login."""
    ip_identifier = normalize_identifier(_client_ip(request))
    username_field = getattr(user, 'USERNAME_FIELD', 'username')
    username_value = getattr(user, username_field, None) or user.get_username()
    username_identifier = normalize_identifier(username_value)

    for kind, identifier in (('ip', ip_identifier), ('user', username_identifier)):
        if identifier:
            _clear_records(kind, identifier)
