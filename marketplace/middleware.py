from django.utils import timezone
from .models import Profile

class UpdateLastSeenMiddleware:
    """
    Middleware to update user's last_seen timestamp on every request
    for more accurate online status detection.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Update last_seen before processing the request
        if request.user.is_authenticated:
            try:
                Profile.objects.filter(user=request.user).update(last_seen=timezone.now())
            except Profile.DoesNotExist:
                # Create profile if it doesn't exist
                Profile.objects.create(user=request.user, last_seen=timezone.now())
        
        response = self.get_response(request)
        return response