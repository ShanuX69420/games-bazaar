# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

admin_base = settings.ADMIN_URL.rstrip('/')

urlpatterns = [
    # Our custom admin chat URLs MUST come before the default admin
    path(f'{admin_base}/chat/', include('marketplace.admin_urls', namespace='admin_chat')),
    path(settings.ADMIN_URL, admin.site.urls),
    path('admin/', RedirectView.as_view(url='/', permanent=False)),
    path('', include('marketplace.urls')),
    path('accounts/', include('allauth.urls')),
]

# Media files: only served by Django in development
# In production, media must be served by Nginx/GCS/CDN (no Django routing)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
