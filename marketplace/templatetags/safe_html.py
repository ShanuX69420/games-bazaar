from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
import re

register = template.Library()

@register.filter
def safe_system_html(value):
    """
    Safely render HTML for system messages.
    Only allows specific safe tags: <a>, <strong>, <em>
    All other content is escaped.
    """
    if not value:
        return value
    
    # First escape everything to be safe
    safe_content = escape(value)
    
    # Now selectively un-escape only the allowed HTML patterns with strict validation
    # Pattern 1: <a href="/path/" class="class-name">text</a>
    # Only allow internal URLs (starting with /)
    safe_content = re.sub(
        r'&lt;a href=&quot;(/[^&"<>]*?)&quot; class=&quot;([a-zA-Z0-9\-_ ]+?)&quot;&gt;([^&<>]+?)&lt;/a&gt;',
        r'<a href="\1" class="\2">\3</a>',
        safe_content,
        flags=re.IGNORECASE
    )
    
    # Pattern 2: <strong>text</strong>
    safe_content = re.sub(
        r'&lt;strong&gt;([^&<>]+?)&lt;/strong&gt;',
        r'<strong>\1</strong>',
        safe_content,
        flags=re.IGNORECASE
    )
    
    # Pattern 3: <em>text</em>
    safe_content = re.sub(
        r'&lt;em&gt;([^&<>]+?)&lt;/em&gt;',
        r'<em>\1</em>',
        safe_content,
        flags=re.IGNORECASE
    )
    
    # Convert line breaks
    safe_content = safe_content.replace('\n', '<br>')
    
    return mark_safe(safe_content)

@register.filter
def safe_user_html(value):
    """
    Safely render HTML for user messages.
    Content is already escaped by backend sanitization, just handle line breaks.
    """
    if not value:
        return value
    
    # Content is already escaped by sanitize_user_input() in backend
    # Just convert line breaks to <br> tags
    safe_content = value.replace('\n', '<br>')
    
    return mark_safe(safe_content)

@register.filter
def unescape_for_preview(value):
    """
    Convert HTML entities back to plain text for message previews.
    Also strips HTML tags from system messages.
    This is safe for previews since the content won't be rendered as HTML.
    """
    if not value:
        return value
    
    import html
    import re
    
    # First, strip any HTML tags (for system messages with actual HTML)
    text_only = re.sub(r'<[^>]+>', '', value)
    
    # Then unescape HTML entities (for user messages with &lt; etc.)
    unescaped_text = html.unescape(text_only)
    
    return unescaped_text