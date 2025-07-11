# marketplace/apps.py
from django.apps import AppConfig

class MarketplaceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'marketplace'

    def ready(self):
        # This line is essential for your signals to work.
        import marketplace.signals