# marketplace/templatetags/time_filters.py
from django import template
from django.utils import timezone
import datetime

register = template.Library()

@register.filter
def relative_time(value):
    if not isinstance(value, datetime.datetime):
        return value

    now = timezone.now()
    today = now.date()
    value_date = value.date()

    if value_date == today:
        return value.strftime("%I:%M %p").lower() # e.g., 10:30 pm
    elif value_date == today - datetime.timedelta(days=1):
        return "yesterday"
    else:
        return value.strftime("%d %b") # e.g., 11 Jul


@register.filter
def smart_time(value):
    if not isinstance(value, datetime.datetime):
        return value

    now = timezone.now()

    if value.date() == now.date():
        return value.strftime("%I:%M %p").lower() # e.g., 10:30 pm
    else:
        return value.strftime("%d.%m.%Y") # e.g., 12.07.2025