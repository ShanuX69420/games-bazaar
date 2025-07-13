# marketplace/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # This is your existing chat consumer
    re_path(r'ws/chat/(?P<username>[\w.@+-]+)/$', consumers.ChatConsumer.as_asgi()),
    # This is the new route for our notification consumer
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
]