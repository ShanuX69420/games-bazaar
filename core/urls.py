# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
# Add this new import
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    # Our custom admin chat URLs MUST come before the default admin
    path('admin/chat/', include('marketplace.admin_urls', namespace='admin_chat')),
    path('admin/', admin.site.urls),
    path('', include('marketplace.urls')),
    path('accounts/', include('allauth.urls')),
]

# This handles user-uploaded media files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # In production, serve media files through Django (temporary fix)
    # Note: For high-traffic production, use nginx/Apache to serve media files
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
