# marketplace/templatetags/grouping_filters.py
from django import template
from itertools import groupby

register = template.Library()

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