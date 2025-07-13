# marketplace/context_processors.py
from .models import Order, Message, Conversation # Correct imports
from django.db.models import Q

def notifications(request):
    if request.user.is_authenticated:
        # Get count of active purchases
        active_purchases_count = Order.objects.filter(buyer=request.user, status='PROCESSING').count()

        # Get count of active sales
        active_sales_count = Order.objects.filter(seller=request.user, status='PROCESSING').count()

        # --- MODIFIED LOGIC ---
        # Get count of conversations with unread messages
        user_conversations = Conversation.objects.filter(Q(participant1=request.user) | Q(participant2=request.user))
        unread_conversations_count = Message.objects.filter(
            conversation__in=user_conversations,
            is_read=False
        ).exclude(sender=request.user).values('conversation').distinct().count()
        # --- END MODIFIED LOGIC ---

        return {
            'active_purchases_count': active_purchases_count,
            'active_sales_count': active_sales_count,
            'unread_conversations_count': unread_conversations_count, # Use the new variable
        }
    return {}