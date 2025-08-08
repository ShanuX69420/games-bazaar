"""
Custom storage classes for handling both local and Google Cloud Storage
for images based on when they were uploaded.
"""

import os
from datetime import datetime
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from storages.backends.gcloud import GoogleCloudStorage


class ConditionalImageStorage:
    """
    Storage class that uses Google Cloud Storage for new images
    and local storage for existing images.
    """
    
    def __init__(self, location=None, base_url=None):
        self.location = location
        self.base_url = base_url
        
        # Initialize both storage backends
        self.local_storage = FileSystemStorage(
            location=os.path.join(settings.MEDIA_ROOT, location or ''),
            base_url=settings.MEDIA_URL + (location + '/' if location else '')
        )
        
        if settings.USE_GCS_FOR_NEW_IMAGES and all([
            settings.GS_BUCKET_NAME,
            settings.GS_PROJECT_ID,
            settings.GS_CREDENTIALS
        ]):
            try:
                # Initialize GCS storage without passing credentials directly
                # The credentials will be picked up from the environment variable
                self.gcs_storage = GoogleCloudStorage(
                    bucket_name=settings.GS_BUCKET_NAME,
                    project_id=settings.GS_PROJECT_ID,
                    custom_endpoint=settings.GS_CUSTOM_ENDPOINT,
                    default_acl=settings.GS_DEFAULT_ACL,
                    file_overwrite=settings.GS_FILE_OVERWRITE,
                    max_memory_size=settings.GS_MAX_MEMORY_SIZE,
                )
                self.use_gcs = True
            except Exception as e:
                print(f"Warning: Could not initialize GCS storage: {e}")
                self.gcs_storage = None
                self.use_gcs = False
        else:
            self.gcs_storage = None
            self.use_gcs = False
    
    def save(self, name, content, max_length=None):
        """Save new files to GCS, existing files to local storage"""
        if self.use_gcs:
            # New images go to Google Cloud Storage
            return self.gcs_storage.save(name, content, max_length)
        else:
            # Fallback to local storage
            return self.local_storage.save(name, content, max_length)
    
    def delete(self, name):
        """Delete from appropriate storage based on where file exists"""
        # Try GCS first if enabled
        if self.use_gcs and self.gcs_storage.exists(name):
            return self.gcs_storage.delete(name)
        # Fallback to local storage
        elif self.local_storage.exists(name):
            return self.local_storage.delete(name)
    
    def exists(self, name):
        """Check if file exists in either storage"""
        if self.use_gcs and self.gcs_storage.exists(name):
            return True
        return self.local_storage.exists(name)
    
    def url(self, name):
        """Get URL for file from appropriate storage"""
        # Always check local storage first for existing images
        if self.local_storage.exists(name):
            return self.local_storage.url(name)
        
        # Only try GCS if enabled and file doesn't exist locally
        if self.use_gcs and self.gcs_storage:
            try:
                if self.gcs_storage.exists(name):
                    return self.gcs_storage.url(name)
            except Exception as e:
                # If GCS fails, fall back to local storage URL construction
                print(f"Warning: GCS URL generation failed: {e}")
        
        # Fallback: return local storage URL even if file doesn't exist
        # This ensures consistent URL structure
        return self.local_storage.url(name)
    
    def size(self, name):
        """Get file size from appropriate storage"""
        if self.use_gcs and self.gcs_storage.exists(name):
            return self.gcs_storage.size(name)
        return self.local_storage.size(name)
    
    def listdir(self, path):
        """List directory contents from appropriate storage"""
        if self.use_gcs:
            return self.gcs_storage.listdir(path)
        return self.local_storage.listdir(path)
    
    def generate_filename(self, filename):
        """Generate filename for new files"""
        # Always use local storage for filename generation to maintain consistency
        return self.local_storage.generate_filename(filename)
    
    def get_valid_name(self, name):
        """Get a valid name for the file"""
        return self.local_storage.get_valid_name(name)
    
    def get_available_name(self, name, max_length=None):
        """Get an available name for the file"""
        return self.local_storage.get_available_name(name, max_length)
    
    def path(self, name):
        """Get local file path"""
        return self.local_storage.path(name)


# Specific storage instances for different image types
class ProfileImageStorage(ConditionalImageStorage):
    """Storage for profile images"""
    def __init__(self):
        super().__init__(location='profile_pics')


class ProductImageStorage(ConditionalImageStorage):
    """Storage for product images"""
    def __init__(self):
        super().__init__(location='product_images')


class ChatImageStorage(ConditionalImageStorage):
    """Storage for chat images"""
    def __init__(self):
        super().__init__(location='chat_images')


# Create instances
profile_image_storage = ProfileImageStorage()
product_image_storage = ProductImageStorage()
chat_image_storage = ChatImageStorage()