# marketplace/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q
from .models import Order, Review, Conversation, Message, Transaction, WithdrawalRequest
from channels.db import database_sync_to_async
from django.template.loader import render_to_string # <-- Add this import

# --- Helper functions to get data from the database ---

def get_user_context(user):
    """Gets all the counts needed for notifications for a specific user."""
    active_purchases = Order.objects.filter(buyer=user, status='PROCESSING').count()
    active_sales = Order.objects.filter(seller=user, status='PROCESSING').count()
    
    user_conversations = Conversation.objects.filter(Q(participant1=user) | Q(participant2=user))
    unread_conversations = Message.objects.filter(
        conversation__in=user_conversations,
        is_read=False
    ).exclude(sender=user).values('conversation').distinct().count()

    return {
        'active_purchases_count': active_purchases,
        'active_sales_count': active_sales,
        'unread_conversations_count': unread_conversations,
    }

def send_system_message(conversation, content, sender_user):
    """
    Creates a system message in a chat.
    The post_save signal on the Message model will handle broadcasting it.
    """
    system_message = Message.objects.create(
        conversation=conversation,
        sender=sender_user,
        content=content,
        is_system_message=True
    )
    return system_message

# --- NEW: Signal handler for when a new message is saved ---

# games-bazaar-master/marketplace/signals.py

@receiver(post_save, sender=Message)
def new_message_handler(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        conversation = instance.conversation
        
        # This new line "touches" the conversation, updating its `updated_at` field.
        # This is the key to sorting your conversations correctly on refresh.
        conversation.save()

        room_group_name = f'chat_{conversation.id}'

        # 1. Broadcast the full message to the active chat window
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'chat_message',
                'message_id': instance.id,
                'message': instance.content,
                'sender': instance.sender.username,
                'timestamp': str(instance.timestamp.isoformat()),
                'is_system_message': instance.is_system_message,
                # --- NEW ---
                'image_url': instance.image.url if instance.image else None
            }
        )

        # 2. Broadcast a notification update to the navbar and conversation list
        for user in [conversation.participant1, conversation.participant2]:
            # The call is now a direct, synchronous function call
            user_context = get_user_context(user)
            notification_group_name = f'notifications_{user.username}'
            
            async_to_sync(channel_layer.group_send)(
                notification_group_name,
                {
                    "type": "send_notification",
                    "notification_type": "new_message",
                    "data": {
                        'unread_conversations_count': user_context['unread_conversations_count'],
                        'conversation_id': conversation.id,
                        'last_message_content': instance.content if instance.content else "[Image]",
                        'last_message_timestamp': str(instance.timestamp.isoformat()),
                        'sender_username': instance.sender.username,
                    },
                }
            )

# --- REBUILT: Signal handler for Orders (The Core of the fix) ---

# games-bazaar-master/marketplace/signals.py

@receiver(post_save, sender=Order)
def order_status_change_handler(sender, instance, created, **kwargs):
    """
    Handles all logic when an order is created or its status changes.
    This sends WebSocket notifications, system messages, and creates/updates transactions.
    """
    channel_layer = get_channel_layer()
    buyer = instance.buyer
    seller = instance.seller

    # --- Part 1: Handle System Messages in Chat ---
    conversation = Conversation.objects.filter(
        (Q(participant1=buyer) & Q(participant2=seller)) |
        (Q(participant1=seller) & Q(participant2=buyer))
    ).first()

    if created and instance.status in ['PROCESSING', 'DELIVERED']:
        if conversation:
            send_system_message(conversation, f"The buyer, {buyer.username}, has paid for order #{instance.id} ({instance.product.listing_title}).", buyer)

    elif not created and instance.tracker.has_changed('status') and instance.status == 'COMPLETED':
        if conversation:
            send_system_message(conversation, f"The buyer has confirmed fulfillment for order #{instance.id}.", buyer)
            
    # --- Part 2: Handle Transaction Creation and Updates ---
    if created or instance.tracker.has_changed('status'):
        status = instance.status

        if status == 'PROCESSING':
            Transaction.objects.update_or_create(
                order=instance, user=buyer, transaction_type='ORDER_PURCHASE',
                defaults={'amount': -instance.total_price, 'status': 'PROCESSING', 'description': f"Purchase of '{instance.product.listing_title}'"}
            )
            Transaction.objects.update_or_create(
                order=instance, user=seller, transaction_type='ORDER_SALE',
                defaults={'amount': instance.total_price, 'status': 'PROCESSING', 'description': f"Sale of '{instance.product.listing_title}'"}
            )
        elif status == 'COMPLETED':
            Transaction.objects.filter(order=instance, user=buyer).update(status='COMPLETED')
            net_earning = instance.total_price - (instance.commission_paid or 0)
            Transaction.objects.filter(order=instance, user=seller).update(status='COMPLETED', amount=net_earning)
        elif status in ['CANCELLED', 'REFUNDED']:
            Transaction.objects.filter(order=instance).update(status=status)
    
    # --- Part 3: Handle Real-time UI Updates ---
    if instance.tracker.has_changed('status') or created:
        buyer_context = get_user_context(buyer)
        seller_context = get_user_context(seller)
        
        if created:
            message_for_ui = f"New order #{instance.id} from {buyer.username}."
        else:
            message_for_ui = f"Order #{instance.id} status updated to {instance.get_status_display()}."

        async_to_sync(channel_layer.group_send)(
            f'notifications_{buyer.username}',
            {
                "type": "send_notification",
                "notification_type": "order_update",
                "data": {
                    "message": f"Your order #{instance.id} status: {instance.get_status_display()}",
                    **buyer_context
                }
            }
        )
        async_to_sync(channel_layer.group_send)(
            f'notifications_{seller.username}',
            {
                "type": "send_notification",
                "notification_type": "order_update",
                "data": {
                    "message": message_for_ui,
                    **seller_context
                }
            }
        )

# --- Other signal handlers can remain, this was the most important one ---
@receiver(post_save, sender=Review)
def review_creation_message(sender, instance, created, **kwargs):
    # This handler is fine as is.
    if created:
        order = instance.order
        buyer = order.buyer
        seller = order.seller
        conversation = Conversation.objects.filter(
            (Q(participant1=buyer) & Q(participant2=seller)) |
            (Q(participant1=seller) & Q(participant2=buyer))
        ).first()

        if conversation:
            send_system_message(conversation, f"The buyer has left a {instance.rating}-star review.", buyer)


@receiver(post_save, sender=WithdrawalRequest)
def withdrawal_transaction_handler(sender, instance, created, **kwargs):
    # This handler is fine as is.
    if created:
        Transaction.objects.create(
            user=instance.user, amount=-instance.amount, transaction_type='WITHDRAWAL',
            status=instance.status, description='Withdrawal Request', withdrawal=instance
        )
    else:
        transaction_status = instance.status
        if instance.status == 'APPROVED': transaction_status = 'COMPLETED'
        elif instance.status == 'REJECTED': transaction_status = 'CANCELLED'
        Transaction.objects.filter(withdrawal=instance).update(status=transaction_status)