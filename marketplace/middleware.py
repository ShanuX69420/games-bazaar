from django.utils import timezone
from django.core.cache import cache
from .models import Profile
import datetime

class UpdateLastSeenMiddleware:
    """
    Optimized middleware to update user's last_seen timestamp efficiently.
    Uses caching to avoid database writes on every request.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Efficiently update last_seen using caching
        if request.user.is_authenticated:
            self._update_last_seen_cached(request.user)
        
        response = self.get_response(request)
        return response
    
    def _update_last_seen_cached(self, user):
        """
        Update last_seen with intelligent caching to minimize database writes.
        Only updates database if user hasn't been seen in last 2 minutes.
        """
        now = timezone.now()
        cache_key = f'user_last_seen_{user.id}'
        
        # Check when we last updated this user's last_seen
        last_db_update = cache.get(cache_key)
        
        if last_db_update is None or (now - last_db_update).total_seconds() > 120:
            # Only update database if more than 2 minutes since last update
            try:
                Profile.objects.filter(user=user).update(last_seen=now)
                # Cache that we updated the database
                cache.set(cache_key, now, 300)  # Cache for 5 minutes
            except Profile.DoesNotExist:
                # Create profile if it doesn't exist
                Profile.objects.create(user=user, last_seen=now)
                cache.set(cache_key, now, 300)