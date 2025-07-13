# marketplace/context_processors.py
from .models import Order, Message, Conversation # Correct imports
from django.db.models import Q

def notifications(request):
    if request.user.is_authenticated:
        active_purchases_count = Order.objects.filter(buyer=request.user, status='PROCESSING').count()
        active_sales_count = Order.objects.filter(seller=request.user, status='PROCESSING').count()
        
        # Get all conversations the user is a part of
        user_conversations = Conversation.objects.filter(Q(participant1=request.user) | Q(participant2=request.user))
        
        # Count messages in those conversations that are unread AND not sent by the current user
        unread_messages_count = Message.objects.filter(
            conversation__in=user_conversations,
            is_read=False
        ).exclude(sender=request.user).count()

        return {
            'active_purchases_count': active_purchases_count,
            'active_sales_count': active_sales_count,
            'unread_messages_count': unread_messages_count,
        }
    return {}