#!/usr/bin/env python
"""
Quick script to clear the home page cache
"""
import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.core.cache import cache

# Clear the home page games cache
cache.delete('home_games_list')
print("Home page cache cleared! Your new game should now appear.")

# Also clear search cache that might be affected
search_keys = cache.get('search_keys', [])
for key in search_keys:
    cache.delete(key)
    
print("Search cache also cleared.")
print("\nRefresh your home page to see the new game!")