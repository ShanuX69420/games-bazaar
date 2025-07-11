# marketplace/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # The change is adding a '?' to make the slash optional: /?$
    re_path(r'ws/chat/(?P<order_id>\d+)/?$', consumers.ChatConsumer.as_asgi()),
]