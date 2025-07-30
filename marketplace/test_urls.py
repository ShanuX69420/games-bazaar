# Minimal URLs for testing
from django.urls import path, include
from django.contrib import admin

# Simple test URLs without allauth
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('marketplace.urls')),
]