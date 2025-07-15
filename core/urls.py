# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
# Add this new import
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('marketplace.urls')),
]

# Serve user-uploaded media files in both development and simple production setups
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# This new line will handle the admin static files
urlpatterns += staticfiles_urlpatterns()