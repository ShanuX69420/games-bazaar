#!/usr/bin/env python3
"""
Minimal Django test server
"""
import os
import sys
import django
from django.conf import settings
from django.http import HttpResponse
from django.urls import path
from django.core.management import execute_from_command_line

# Minimal Django settings
settings.configure(
    DEBUG=True,
    SECRET_KEY='test-key-123',
    ALLOWED_HOSTS=['127.0.0.1', 'localhost'],
    ROOT_URLCONF=__name__,
    MIDDLEWARE=[
        'django.middleware.common.CommonMiddleware',
    ],
    INSTALLED_APPS=[
        'django.contrib.contenttypes',
        'django.contrib.auth',
    ],
)

def hello_view(request):
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🚀 Django Test Success!</title>
        <style>
            body { font-family: Arial; text-align: center; padding: 50px; background: #e8f5e8; }
            .success { color: #28a745; font-size: 24px; }
        </style>
    </head>
    <body>
        <h1 class="success">🎉 Django Works!</h1>
        <p>Your Django server is working correctly!</p>
        <p>This means the issue is with your main project configuration.</p>
        <hr>
        <p><strong>Django Version:</strong> {django_version}</p>
        <p><strong>Python Version:</strong> {python_version}</p>
    </body>
    </html>
    """.format(
        django_version=django.get_version(),
        python_version=sys.version
    )
    return HttpResponse(html)

urlpatterns = [
    path('', hello_view, name='hello'),
]

if __name__ == '__main__':
    print("🚀 Starting Minimal Django Server...")
    print("📡 Server: http://127.0.0.1:8080")
    print("🛑 Press Ctrl+C to stop")
    print()
    
    django.setup()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', __name__)
    execute_from_command_line(['manage.py', 'runserver', '127.0.0.1:8080'])