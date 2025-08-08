# marketplace/templatetags/grouping_filters.py
from django import template
from itertools import groupby

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Returns the value of a dictionary key.
    Usage: {{ my_dictionary|get_item:my_key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def group_by(value, arg):
    """
    Groups a list of objects by a specific attribute or index.
    This version is more robust and handles potential errors gracefully.
    """
    if not hasattr(value, '__iter__'):
        return []

    # Define the key function that will get the value to group by
    def key_func(item):
        try:
            keys = arg.split('.')
            val = item
            for key in keys:
                if key.isdigit() and isinstance(val, (str, list, tuple)):
                    # Handle indexing for strings, lists, or tuples
                    val = val[int(key)]
                else:
                    # Handle attribute access for objects
                    val = getattr(val, key)
            return val
        except (AttributeError, IndexError, TypeError):
            # If any part of the access fails (e.g., empty title), return None
            return None

    # Before sorting, filter out any items where the key function returned None
    # This is the crucial step that prevents the TypeError
    filtered_value = [item for item in value if key_func(item) is not None]

    if not filtered_value:
        return []

    # Sort the filtered list using the same key function
    sorted_value = sorted(filtered_value, key=key_func)

    # Group the sorted items and return the final structure
    return [{'grouper': key, 'list': list(items)} for key, items in groupby(sorted_value, key=key_func)]

@register.filter
def get_option_for_filter(listing, primary_filter):
    """
    Finds and returns the filter option from a listing that matches the primary filter.
    e.g., given a primary_filter for "Platform", it finds "PC" or "PS5" on the listing.
    """
    if not primary_filter or not hasattr(listing, 'filter_options'):
        return None
    # This uses prefetched data from the view, so it's efficient.
    for option in listing.filter_options.all():
        if option.filter_id == primary_filter.id:
            return option
    return None