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

@register.filter
def simple_time_since(value):
    if not isinstance(value, datetime.datetime):
        return value

    now = timezone.now()
    # Calculate the difference in months
    months = (now.year - value.year) * 12 + (now.month - value.month)

    if months <= 0:
        return "this month"
    elif months == 1:
        return "1 month ago"
    else:
        return f"{months} months ago"


@register.filter
def registration_duration(value):
    """
    Returns a simplified string of how long ago a date was.
    e.g., "1 month", "8 months", "1 year", "3 years".
    """
    if not isinstance(value, (datetime.datetime, datetime.date)):
        return value

    if isinstance(value, datetime.date):
        value = datetime.datetime.combine(value, datetime.time.min)
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_default_timezone())

    now = timezone.now()

    # Calculate years
    years = now.year - value.year
    if (now.month, now.day) < (value.month, value.day):
        years -= 1

    if years >= 1:
        return f"{years} year{'s' if years > 1 else ''}"

    # Calculate months if it's less than a year
    months = (now.year - value.year) * 12 + (now.month - value.month)

    # If the user registered in the current month, show "1 month"
    if months < 1:
        months = 1

    return f"{months} month{'s' if months > 1 else ''}"