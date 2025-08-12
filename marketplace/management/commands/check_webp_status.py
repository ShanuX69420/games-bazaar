from django.core.management.base import BaseCommand
from django.conf import settings
from marketplace.models import ProductImage


class Command(BaseCommand):
    help = 'Check WebP conversion status'

    def handle(self, *args, **options):
        self.stdout.write('=== WebP Conversion Status Check ===\n')
        
        # Check settings
        self.stdout.write(f'GCS Enabled: {settings.USE_GCS_FOR_NEW_IMAGES}')
        self.stdout.write(f'GCS Endpoint: {settings.GS_CUSTOM_ENDPOINT}')
        self.stdout.write(f'GCS Bucket: {settings.GS_BUCKET_NAME}\n')
        
        # Check recent ProductImages
        recent_images = ProductImage.objects.order_by('-id')[:10]
        self.stdout.write('=== Recent Product Images ===')
        
        webp_count = 0
        total_count = len(recent_images)
        
        for img in recent_images:
            filename = img.image.name if img.image else 'No file'
            is_webp = filename.lower().endswith('.webp')
            if is_webp:
                webp_count += 1
            
            try:
                url = img.image_url
            except:
                url = 'Error getting URL'
            
            status = '[WebP]' if is_webp else '[NOT WebP]'
            self.stdout.write(f'{status} | {filename}')
            self.stdout.write(f'    URL: {url}\n')
        
        self.stdout.write(f'Summary: {webp_count}/{total_count} recent images are WebP format\n')
        
        self.stdout.write('=== How to Verify WebP is Working ===')
        self.stdout.write('1. Upload a new product image')
        self.stdout.write('2. Check if filename ends with .webp in the list above')
        self.stdout.write('3. Open Chrome DevTools → Network tab')
        self.stdout.write('4. Look for image requests ending in .webp')
        self.stdout.write('5. WebP files should be 40-60% smaller than original')