# core/asgi.py
import os
from django.core.asgi import get_asgi_application

# This line MUST come first to set up Django.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# This line initializes Django's HTTP application.
# The WhiteNoise middleware from settings.py will handle static files automatically.
django_asgi_app = get_asgi_application()

# Now we import the parts for our chat application.
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
import marketplace.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            marketplace.routing.websocket_urlpatterns
        )
    ),
})