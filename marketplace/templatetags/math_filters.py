# marketplace/templatetags/math_filters.py
from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    # If the commission (arg) is None, treat it as 0
    if arg is None:
        arg = 0
    return value - arg