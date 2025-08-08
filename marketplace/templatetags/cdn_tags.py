"""
Template tags for CDN URL generation
"""
from django import template
from django.conf import settings
import os

register = template.Library()


@register.filter
def cdn_url(image_field, folder='images'):
    """
    Convert an ImageField to CDN URL if GCS is enabled
    Usage: {{ profile.image|cdn_url:'profile_pics' }}
    """
    if not image_field or not hasattr(image_field, 'url'):
        return None
        
    # Check if we should serve via CDN
    if hasattr(settings, 'USE_GCS_FOR_NEW_IMAGES') and settings.USE_GCS_FOR_NEW_IMAGES:
        if hasattr(settings, 'GS_CUSTOM_ENDPOINT') and settings.GS_CUSTOM_ENDPOINT:
            # Return CDN URL directly
            filename = os.path.basename(image_field.name)
            return f"{settings.GS_CUSTOM_ENDPOINT}/{folder}/{filename}"
    
    # Fallback to regular URL
    return image_field.url


@register.simple_tag
def profile_image_url(profile):
    """
    Get profile image CDN URL
    Usage: {% profile_image_url user.profile %}
    """
    if profile.image:
        return cdn_url(profile.image, 'profile_pics')
    return '/static/images/default.jpg'


@register.simple_tag  
def product_image_url(product_image):
    """
    Get product image CDN URL
    Usage: {% product_image_url image %}
    """
    if product_image.image:
        return cdn_url(product_image.image, 'product_images')
    return None