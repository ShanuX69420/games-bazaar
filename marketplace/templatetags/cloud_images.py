"""
Template tags for handling cloud storage images
"""
from django import template
from django.conf import settings
import os

register = template.Library()


@register.simple_tag
def cloud_image_url(image_field):
    """
    Return Google Cloud Storage URL if available and enabled,
    otherwise return local media URL
    """
    if not image_field:
        return '/static/images/default.jpg'
    
    # Always return local URL for now - we can enhance this later
    try:
        return image_field.url
    except (ValueError, AttributeError):
        return '/static/images/default.jpg'


@register.simple_tag  
def gcs_image_url(image_path, image_type='chat_images'):
    """
    Generate Google Cloud Storage URL for an image
    Args:
        image_path: relative path to the image (e.g., 'image.jpg')  
        image_type: type of image ('chat_images', 'profile_pics', 'product_images')
    """
    if not image_path:
        return '/static/images/default.jpg'
        
    if not settings.USE_GCS_FOR_NEW_IMAGES:
        # Return local media URL
        return f"{settings.MEDIA_URL}{image_type}/{image_path}"
    
    # Check if we have GCS configured
    if not all([settings.GS_BUCKET_NAME, settings.GS_CUSTOM_ENDPOINT]):
        return f"{settings.MEDIA_URL}{image_type}/{image_path}"
    
    # Return GCS URL with custom domain
    filename = os.path.basename(image_path) 
    return f"{settings.GS_CUSTOM_ENDPOINT}/{image_type}/{filename}"


@register.filter
def smart_image_url(image_field):
    """
    Smart image URL that checks local first, then cloud
    Usage: {{ message.image|smart_image_url }}
    """
    if not image_field:
        return '/static/images/default.jpg'
    
    try:
        # For now, just return the regular URL
        # Later we can add logic to check if file exists in GCS
        return image_field.url
    except (ValueError, AttributeError):
        return '/static/images/default.jpg'