"""
Management command to sync existing local images to CDN structure
This preserves existing functionality while enabling CDN serving
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from marketplace.models import Message, Profile, ProductImage
import os


class Command(BaseCommand):
    help = 'Sync existing local images to Google Cloud Storage CDN structure'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without actually doing it',
        )
        parser.add_argument(
            '--model',
            choices=['message', 'profile', 'product', 'all'],
            default='all',
            help='Which model images to sync',
        )

    def handle(self, *args, **options):
        if not settings.USE_GCS_FOR_NEW_IMAGES:
            self.stdout.write(
                self.style.WARNING('Google Cloud Storage is not enabled. Set USE_GCS_FOR_NEW_IMAGES=True')
            )
            return

        dry_run = options['dry_run']
        model_choice = options['model']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No actual sync will occur'))

        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(settings.GS_BUCKET_NAME)
            
            if not bucket.exists():
                self.stdout.write(
                    self.style.ERROR(f'Bucket {settings.GS_BUCKET_NAME} does not exist')
                )
                return
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to connect to Google Cloud Storage: {e}')
            )
            return

        if model_choice in ['message', 'all']:
            self.sync_message_images(bucket, dry_run)
            
        if model_choice in ['profile', 'all']:
            self.sync_profile_images(bucket, dry_run)
            
        if model_choice in ['product', 'all']:
            self.sync_product_images(bucket, dry_run)

    def sync_message_images(self, bucket, dry_run):
        """Sync chat message images"""
        self.stdout.write('Syncing message images...')
        
        messages = Message.objects.filter(image__isnull=False).exclude(image='')
        count = 0
        
        for message in messages:
            if message.image:
                try:
                    local_path = message.image.path
                    if os.path.exists(local_path):
                        blob_name = f"chat_images/{os.path.basename(message.image.name)}"
                        
                        # Check if blob already exists
                        blob = bucket.blob(blob_name)
                        if blob.exists():
                            self.stdout.write(f'EXISTS: {blob_name}')
                            continue
                        
                        if not dry_run:
                            try:
                                import mimetypes
                                content_type, _ = mimetypes.guess_type(local_path)
                                if content_type and content_type.startswith('image/'):
                                    blob.content_type = content_type
                                
                                blob.upload_from_filename(local_path)
                                self.stdout.write(f'SUCCESS: Uploaded: {blob_name}')
                                count += 1
                            except Exception as e:
                                self.stdout.write(
                                    self.style.ERROR(f'ERROR: Failed to upload {blob_name}: {e}')
                                )
                        else:
                            self.stdout.write(f'Would upload: {blob_name}')
                            count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'WARNING: Could not process message image {message.id}: {e}')
                    )
        
        self.stdout.write(
            self.style.SUCCESS(f'Message images {"would be " if dry_run else ""}synced: {count}')
        )

    def sync_profile_images(self, bucket, dry_run):
        """Sync profile images"""
        self.stdout.write('Syncing profile images...')
        
        profiles = Profile.objects.filter(image__isnull=False).exclude(image='')
        count = 0
        
        for profile in profiles:
            if profile.image:
                try:
                    local_path = profile.image.path
                    if os.path.exists(local_path):
                        blob_name = f"profile_pics/{os.path.basename(profile.image.name)}"
                        
                        # Check if blob already exists
                        blob = bucket.blob(blob_name)
                        if blob.exists():
                            self.stdout.write(f'EXISTS: {blob_name}')
                            continue
                        
                        if not dry_run:
                            try:
                                import mimetypes
                                content_type, _ = mimetypes.guess_type(local_path)
                                if content_type and content_type.startswith('image/'):
                                    blob.content_type = content_type
                                
                                blob.upload_from_filename(local_path)
                                self.stdout.write(f'SUCCESS: Uploaded: {blob_name}')
                                count += 1
                            except Exception as e:
                                self.stdout.write(
                                    self.style.ERROR(f'ERROR: Failed to upload {blob_name}: {e}')
                                )
                        else:
                            self.stdout.write(f'Would upload: {blob_name}')
                            count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'WARNING: Could not process profile image {profile.id}: {e}')
                    )
        
        self.stdout.write(
            self.style.SUCCESS(f'Profile images {"would be " if dry_run else ""}synced: {count}')
        )

    def sync_product_images(self, bucket, dry_run):
        """Sync product images"""
        self.stdout.write('Syncing product images...')
        
        product_images = ProductImage.objects.filter(image__isnull=False).exclude(image='')
        count = 0
        
        for product_image in product_images:
            if product_image.image:
                try:
                    local_path = product_image.image.path
                    if os.path.exists(local_path):
                        blob_name = f"product_images/{os.path.basename(product_image.image.name)}"
                        
                        # Check if blob already exists
                        blob = bucket.blob(blob_name)
                        if blob.exists():
                            self.stdout.write(f'EXISTS: {blob_name}')
                            continue
                        
                        if not dry_run:
                            try:
                                import mimetypes
                                content_type, _ = mimetypes.guess_type(local_path)
                                if content_type and content_type.startswith('image/'):
                                    blob.content_type = content_type
                                
                                blob.upload_from_filename(local_path)
                                self.stdout.write(f'SUCCESS: Uploaded: {blob_name}')
                                count += 1
                            except Exception as e:
                                self.stdout.write(
                                    self.style.ERROR(f'ERROR: Failed to upload {blob_name}: {e}')
                                )
                        else:
                            self.stdout.write(f'Would upload: {blob_name}')
                            count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(f'WARNING: Could not process product image {product_image.id}: {e}')
                    )
        
        self.stdout.write(
            self.style.SUCCESS(f'Product images {"would be " if dry_run else ""}synced: {count}')
        )