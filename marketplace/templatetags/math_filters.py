# marketplace/templatetags/math_filters.py
from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    # If the commission (arg) is None, treat it as 0
    if arg is None:
        arg = 0
    return value - arg

@register.filter
def star_fill_percentage(rating):
    """Convert rating to percentage for partial star fills. Rating 0-5 -> 0-100%"""
    try:
        rating_float = float(rating) if rating else 0
        # Clamp between 0 and 5, then convert to percentage (0-100%)
        clamped = max(0, min(5, rating_float))
        return clamped * 20  # 5 stars * 20% each = 100%
    except (ValueError, TypeError):
        return 0