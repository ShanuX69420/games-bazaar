# marketplace/context_processors.py
from .models import Order, Message, Conversation, Game
from django.db.models import Q
from django.conf import settings
from django.core.cache import cache

def notifications(request):
    # Cache total games count for 30 minutes (rarely changes)
    cache_key = 'total_games_count'
    total_games_count = cache.get(cache_key)
    if total_games_count is None:
        total_games_count = Game.objects.count()
        cache.set(cache_key, total_games_count, 1800)  # 30 minutes

    # This context is available on all pages for all users
    context = {
        'total_games_count': total_games_count,
        'RECAPTCHA_PUBLIC_KEY': settings.RECAPTCHA_PUBLIC_KEY,
    }

    if request.user.is_authenticated:
        # Cache user notification counts for 60 seconds (frequently changing)
        user_cache_key = f'user_notifications_{request.user.id}'
        cached_counts = cache.get(user_cache_key)
        
        if cached_counts is None:
            # Get count of active purchases
            active_purchases_count = Order.objects.filter(buyer=request.user, status='PROCESSING').count()

            # Get count of active sales
            active_sales_count = Order.objects.filter(seller=request.user, status='PROCESSING').count()

            # Get count of conversations with unread messages
            user_conversations = Conversation.objects.filter(Q(participant1=request.user) | Q(participant2=request.user))
            unread_conversations_count = Message.objects.filter(
                conversation__in=user_conversations,
                is_read=False
            ).exclude(sender=request.user).values('conversation').distinct().count()

            cached_counts = {
                'active_purchases_count': active_purchases_count,
                'active_sales_count': active_sales_count,
                'unread_conversations_count': unread_conversations_count,
            }
            
            # Cache for 60 seconds - balance between freshness and performance
            cache.set(user_cache_key, cached_counts, 60)

        # Add user-specific counts to the context
        context.update(cached_counts)

    return context