"""
Management command to migrate images to Google Cloud Storage.
This allows gradual migration without breaking existing functionality.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from marketplace.models import Message, Profile, ProductImage
import os


class Command(BaseCommand):
    help = 'Migrate images to Google Cloud Storage'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually doing it',
        )
        parser.add_argument(
            '--model',
            choices=['message', 'profile', 'product', 'all'],
            default='all',
            help='Which model images to migrate',
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
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No actual migration will occur'))

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
            self.migrate_message_images(bucket, dry_run)
            
        if model_choice in ['profile', 'all']:
            self.migrate_profile_images(bucket, dry_run)
            
        if model_choice in ['product', 'all']:
            self.migrate_product_images(bucket, dry_run)

    def migrate_message_images(self, bucket, dry_run):
        """Migrate chat message images"""
        self.stdout.write('Migrating message images...')
        
        messages = Message.objects.filter(image__isnull=False).exclude(image='')
        count = 0
        
        for message in messages:
            if message.image:
                local_path = message.image.path
                if os.path.exists(local_path):
                    blob_name = f"chat_images/{os.path.basename(message.image.name)}"
                    
                    if not dry_run:
                        try:
                            blob = bucket.blob(blob_name)
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
        
        self.stdout.write(
            self.style.SUCCESS(f'Message images {"would be " if dry_run else ""}migrated: {count}')
        )

    def migrate_profile_images(self, bucket, dry_run):
        """Migrate profile images"""
        self.stdout.write('Migrating profile images...')
        
        profiles = Profile.objects.filter(image__isnull=False).exclude(image='')
        count = 0
        
        for profile in profiles:
            if profile.image:
                local_path = profile.image.path
                if os.path.exists(local_path):
                    blob_name = f"profile_pics/{os.path.basename(profile.image.name)}"
                    
                    if not dry_run:
                        try:
                            blob = bucket.blob(blob_name)
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
        
        self.stdout.write(
            self.style.SUCCESS(f'Profile images {"would be " if dry_run else ""}migrated: {count}')
        )

    def migrate_product_images(self, bucket, dry_run):
        """Migrate product images"""
        self.stdout.write('Migrating product images...')
        
        product_images = ProductImage.objects.filter(image__isnull=False).exclude(image='')
        count = 0
        
        for product_image in product_images:
            if product_image.image:
                local_path = product_image.image.path
                if os.path.exists(local_path):
                    blob_name = f"product_images/{os.path.basename(product_image.image.name)}"
                    
                    if not dry_run:
                        try:
                            blob = bucket.blob(blob_name)
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
        
        self.stdout.write(
            self.style.SUCCESS(f'Product images {"would be " if dry_run else ""}migrated: {count}')
        )