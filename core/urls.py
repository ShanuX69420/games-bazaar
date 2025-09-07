# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Our custom admin chat URLs MUST come before the default admin
    path('admin/chat/', include('marketplace.admin_urls', namespace='admin_chat')),
    path('admin/', admin.site.urls),
    path('', include('marketplace.urls')),
    path('accounts/', include('allauth.urls')),
]

# Media files: only served by Django in development
# In production, media must be served by Nginx/GCS/CDN (no Django routing)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
