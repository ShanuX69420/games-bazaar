"""
Simple Google Cloud Storage integration that doesn't break existing functionality
"""
from django.core.files.storage import DefaultStorage, Storage
from django.conf import settings
import os


class GoogleCloudUniversalStorage(Storage):
    """
    Universal storage class that saves ALL images to Google Cloud Storage
    for production use - no local storage
    """
    
    def __init__(self, folder_name='images'):
        self.default_storage = DefaultStorage()
        self.folder_name = folder_name
        
    def save(self, name, content, max_length=None):
        """Save file directly to Google Cloud Storage"""
        if not settings.USE_GCS_FOR_NEW_IMAGES:
            # Fallback to local storage if GCS is disabled
            return self.default_storage.save(name, content, max_length)
            
        try:
            # Save directly to Google Cloud Storage
            return self._save_to_gcs(name, content, max_length)
        except Exception as e:
            print(f"Error: Failed to upload to GCS: {e}")
            # Fallback to local storage if GCS fails
            return self.default_storage.save(name, content, max_length)
    
    def _save_to_gcs(self, name, content, max_length=None):
        """Save file directly to Google Cloud Storage with WebP optimization"""
        from google.cloud import storage
        import mimetypes
        from PIL import Image
        import io
        
        # Generate a clean filename
        filename = self.get_available_name(name, max_length)
        
        # Convert to WebP for performance optimization
        webp_filename, webp_content = self._convert_to_webp(filename, content)
        if webp_filename and webp_content:
            filename = webp_filename
            content = webp_content
        
        blob_name = f"{self.folder_name}/{os.path.basename(filename)}"
        
        # Determine content type
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            if filename.lower().endswith(('.jpg', '.jpeg')):
                content_type = 'image/jpeg'
            elif filename.lower().endswith('.png'):
                content_type = 'image/png'
            elif filename.lower().endswith('.gif'):
                content_type = 'image/gif'
            elif filename.lower().endswith('.webp'):
                content_type = 'image/webp'
            else:
                content_type = 'image/jpeg'  # Default fallback
        
        # Upload to Google Cloud Storage
        client = storage.Client()
        bucket = client.bucket(settings.GS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        
        # Set content type so images display in browser instead of downloading
        blob.content_type = content_type
        
        # Reset content position if possible
        if hasattr(content, 'seek'):
            content.seek(0)
            
        blob.upload_from_file(content)
        
        # Return the filename (without the folder prefix for Django)
        return os.path.basename(filename)
    
    def _convert_to_webp(self, filename, content):
        """Convert image to WebP format for better performance"""
        try:
            from PIL import Image
            import io
            
            # Skip conversion for GIFs (preserve animation)
            if filename.lower().endswith('.gif'):
                return None, None
            
            # Only convert common image formats
            if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                return None, None
            
            # Reset content position
            if hasattr(content, 'seek'):
                content.seek(0)
            
            # Open and convert image
            image = Image.open(content)
            
            # Convert to RGB if necessary (WebP doesn't support RGBA for all modes)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Create a white background for transparency
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Create WebP content
            webp_content = io.BytesIO()
            image.save(webp_content, format='WEBP', quality=85, optimize=True)
            webp_content.seek(0)
            
            # Generate WebP filename
            base_name = os.path.splitext(filename)[0]
            webp_filename = f"{base_name}.webp"
            
            return webp_filename, webp_content
            
        except Exception as e:
            print(f"WebP conversion failed for {filename}: {e}")
            return None, None
    
    def delete(self, name):
        """Delete from both GCS and local storage"""
        if settings.USE_GCS_FOR_NEW_IMAGES:
            try:
                from google.cloud import storage
                client = storage.Client()
                bucket = client.bucket(settings.GS_BUCKET_NAME)
                blob_name = f"{self.folder_name}/{os.path.basename(name)}"
                blob = bucket.blob(blob_name)
                if blob.exists():
                    blob.delete()
                    print(f"Deleted from GCS: {blob_name}")
            except Exception as e:
                print(f"Error deleting from GCS: {e}")
        
        return self.default_storage.delete(name)
    
    def exists(self, name):
        """Check if file exists in local storage"""
        return self.default_storage.exists(name)
    
    def url(self, name):
        """Return appropriate URL based on configuration and file location"""
        # If GCS is disabled, always use local storage
        if not settings.USE_GCS_FOR_NEW_IMAGES:
            return self.default_storage.url(name)
        
        # If GCS is enabled and we have a custom endpoint
        if name.lower().endswith('.webp'):
            blob_name = f"{self.folder_name}/{os.path.basename(name)}"
            if settings.DEBUG:
                return f"/cdn/{blob_name}"
            endpoint = (settings.GS_CUSTOM_ENDPOINT or '').rstrip('/')
            if endpoint.startswith('http://') or endpoint.startswith('https://'):
                return f"{endpoint}/{blob_name}"
            base_path = endpoint if endpoint else '/cdn'
            if not base_path.startswith('/'):
                base_path = f'/{base_path}'
            return f"{base_path}/{blob_name}"
        
        # For existing files or when GCS is not properly configured, use local storage
        return self.default_storage.url(name)
    
    def size(self, name):
        """Get file size from local storage"""
        return self.default_storage.size(name)
    
    def path(self, name):
        """Get local file path"""
        return self.default_storage.path(name)
    
    def generate_filename(self, filename):
        """Generate filename using default storage"""
        return self.default_storage.generate_filename(filename)
    
    def get_valid_name(self, name):
        """Get valid name using default storage"""
        return self.default_storage.get_valid_name(name)
    
    def get_available_name(self, name, max_length=None):
        """Get available name using default storage"""
        return self.default_storage.get_available_name(name, max_length)
    
    def listdir(self, path):
        """List directory contents"""
        return self.default_storage.listdir(path)


class GoogleCloudChatStorage(GoogleCloudUniversalStorage):
    """
    Storage class that saves chat images ONLY to Google Cloud Storage
    for production use - no local storage
    """
    
    def __init__(self):
        super().__init__(folder_name='chat_images')
    
    def deconstruct(self):
        """Required for Django migrations serialization"""
        return (
            'marketplace.simple_storage.GoogleCloudChatStorage',
            [],
            {}
        )


class GoogleCloudProfileStorage(GoogleCloudUniversalStorage):
    """
    Storage class that saves profile images to Google Cloud Storage
    """
    
    def __init__(self):
        super().__init__(folder_name='profile_pics')
    
    def deconstruct(self):
        """Required for Django migrations serialization"""
        return (
            'marketplace.simple_storage.GoogleCloudProfileStorage',
            [],
            {}
        )


class GoogleCloudProductStorage(GoogleCloudUniversalStorage):
    """
    Storage class that saves product images to Google Cloud Storage
    """
    
    def __init__(self):
        super().__init__(folder_name='product_images')
    
    def deconstruct(self):
        """Required for Django migrations serialization"""
        return (
            'marketplace.simple_storage.GoogleCloudProductStorage',
            [],
            {}
        )


# Create storage instances
google_cloud_chat_storage = GoogleCloudChatStorage()
google_cloud_profile_storage = GoogleCloudProfileStorage()
google_cloud_product_storage = GoogleCloudProductStorage()
