from django.core.management.base import BaseCommand
from django.conf import settings
from marketplace.models import ProductImage, Profile, Message
from PIL import Image
import io
import os


class Command(BaseCommand):
    help = 'Migrate existing images to WebP format in Google Cloud Storage'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without making changes')
        parser.add_argument('--limit', type=int, default=50, help='Limit number of images to process')

    def handle(self, *args, **options):
        if not settings.USE_GCS_FOR_NEW_IMAGES:
            self.stdout.write(self.style.ERROR('GCS is not enabled. Set USE_GCS_FOR_NEW_IMAGES=True'))
            return

        dry_run = options['dry_run']
        limit = options['limit']
        
        self.stdout.write(f'Starting image migration (dry_run={dry_run}, limit={limit})')
        
        # Migrate ProductImages
        product_images = ProductImage.objects.filter(
            image__isnull=False
        ).exclude(
            image__icontains='.webp'
        )[:limit]
        
        self.stdout.write(f'Found {product_images.count()} product images to migrate')
        
        for i, product_image in enumerate(product_images, 1):
            self.stdout.write(f'Processing {i}/{len(product_images)}: {product_image.image.name}')
            
            if dry_run:
                self.stdout.write(f'  Would convert: {product_image.image.name} -> WebP')
                continue
            
            try:
                # Convert and save image
                self._convert_image_to_webp(product_image)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Converted: {product_image.image.name}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Failed: {e}'))
    
    def _convert_image_to_webp(self, product_image):
        """Convert image to WebP and update the model"""
        # Open the current image file
        try:
            current_image = Image.open(product_image.image.path)
        except:
            # If local file doesn't exist, skip
            self.stdout.write(f'  Local file not found, skipping: {product_image.image.name}')
            return
        
        # Convert to RGB if necessary
        if current_image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', current_image.size, (255, 255, 255))
            if current_image.mode == 'P':
                current_image = current_image.convert('RGBA')
            background.paste(current_image, mask=current_image.split()[-1] if current_image.mode == 'RGBA' else None)
            current_image = background
        elif current_image.mode != 'RGB':
            current_image = current_image.convert('RGB')
        
        # Create WebP content
        webp_content = io.BytesIO()
        current_image.save(webp_content, format='WEBP', quality=85, optimize=True)
        webp_content.seek(0)
        
        # Generate new filename
        old_name = product_image.image.name
        base_name = os.path.splitext(os.path.basename(old_name))[0]
        new_name = f"product_images/{base_name}.webp"
        
        # Save the new WebP image
        from django.core.files.base import ContentFile
        product_image.image.save(
            new_name,
            ContentFile(webp_content.getvalue()),
            save=True
        )
        
        self.stdout.write(f'    Saved as: {new_name}')