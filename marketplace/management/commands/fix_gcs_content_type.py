"""
Management command to fix content-type headers for existing images in Google Cloud Storage
"""

from django.core.management.base import BaseCommand
from django.conf import settings
import mimetypes


class Command(BaseCommand):
    help = 'Fix content-type headers for images in Google Cloud Storage'

    def handle(self, *args, **options):
        if not settings.USE_GCS_FOR_NEW_IMAGES:
            self.stdout.write(
                self.style.WARNING('Google Cloud Storage is not enabled')
            )
            return

        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(settings.GS_BUCKET_NAME)
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to connect to Google Cloud Storage: {e}')
            )
            return

        # Fix content-type for all images in chat_images folder
        blobs = bucket.list_blobs(prefix='chat_images/')
        fixed_count = 0
        
        for blob in blobs:
            # Determine correct content type
            content_type, _ = mimetypes.guess_type(blob.name)
            
            if not content_type:
                if blob.name.lower().endswith(('.jpg', '.jpeg')):
                    content_type = 'image/jpeg'
                elif blob.name.lower().endswith('.png'):
                    content_type = 'image/png'
                elif blob.name.lower().endswith('.gif'):
                    content_type = 'image/gif'
                elif blob.name.lower().endswith('.webp'):
                    content_type = 'image/webp'
                else:
                    continue  # Skip non-image files
            
            # Update content type if it's wrong
            if blob.content_type != content_type:
                blob.content_type = content_type
                blob.patch()
                self.stdout.write(f'Fixed: {blob.name} -> {content_type}')
                fixed_count += 1
            else:
                self.stdout.write(f'OK: {blob.name} already has {content_type}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Fixed content-type for {fixed_count} images')
        )