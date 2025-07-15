from django import template
import os
import time
from django.conf import settings

register = template.Library()

@register.filter
def cache_bust(value):
    if hasattr(value, 'path') and os.path.exists(value.path):
        try:
            timestamp = int(os.path.getmtime(value.path))
            return f"{value.url}?v={timestamp}"
        except (ValueError, TypeError):
            pass
    if hasattr(value, 'url'):
        return value.url
    return settings.CACHE_BUST_STRING if hasattr(settings, 'CACHE_BUST_STRING') else ''
