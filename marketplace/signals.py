# marketplace/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q
from .models import Order, Review, Conversation, Message, User
from channels.db import database_sync_to_async

# --- NEW ASYNC HELPER FUNCTIONS ---

@database_sync_to_async
def get_unread_conversation_count(user):
    """
    Calculates the total number of conversations with unread messages for a user.
    This logic is now consistent across the entire application.
    """
    user_conversations = Conversation.objects.filter(Q(participant1=user) | Q(participant2=user))
    return Message.objects.filter(
        conversation__in=user_conversations,
        is_read=False
    ).exclude(sender=user).values('conversation').distinct().count()

async def send_message_notification(user):
    """
    Sends a notification to update the user's main 'Messages' badge.
    """
    count = await get_unread_conversation_count(user)
    channel_layer = get_channel_layer()
    notification_group_name = f'notifications_{user.username}'

    await channel_layer.group_send(
        notification_group_name,
        {
            "type": "send_notification",
            "notification_type": "new_message",
            "data": {'unread_conversations_count': count},
        }
    )

@database_sync_to_async
def get_order_counts(user):
    """
    Get the counts of active purchases and sales for a user.
    """
    active_purchases_count = Order.objects.filter(buyer=user, status='PROCESSING').count()
    active_sales_count = Order.objects.filter(seller=user, status='PROCESSING').count()
    return {
        'active_purchases_count': active_purchases_count,
        'active_sales_count': active_sales_count,
    }

async def send_order_update_notification(user):
    """
    Fetches the latest order counts and sends them to the user's notification group.
    """
    counts = await get_order_counts(user)
    channel_layer = get_channel_layer()
    notification_group_name = f'notifications_{user.username}'

    await channel_layer.group_send(
        notification_group_name,
        {
            "type": "send_notification",
            "notification_type": "order_update",
            "data": counts,
        }
    )

# --- END NEW ASYNC HELPER FUNCTIONS ---


def send_system_message(conversation, content, sender_user):
    """
    This function now only creates the message and sends it to the chat room.
    The navbar notification is handled separately by the signal handlers.
    """
    system_message = Message.objects.create(
        conversation=conversation,
        sender=sender_user,
        content=content,
        is_system_message=True
    )
    channel_layer = get_channel_layer()
    room_group_name = f'chat_{conversation.id}'
    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'chat_message',
            'message': system_message.content,
            'sender': 'Gamers Market',
            'timestamp': str(system_message.timestamp.isoformat()),
            'is_system_message': True
        }
    )

@receiver(post_save, sender=Order)
def order_signal_handler(sender, instance, created, **kwargs):
    buyer = instance.buyer
    seller = instance.seller

    # Find the conversation between the buyer and seller
    conversation = Conversation.objects.filter(
        (Q(participant1=buyer) & Q(participant2=seller)) |
        (Q(participant1=seller) & Q(participant2=buyer))
    ).first()

    # Determine message content and the recipient of the notification
    message_content = None
    notification_recipient = None

    if created and instance.status == 'PROCESSING':
        message_content = f"The buyer, {buyer.username}, has paid for order #{instance.id} ({instance.product.listing_title})."
        notification_recipient = seller # Notify the seller of the new sale
    elif not created and instance.tracker.has_changed('status') and instance.status == 'COMPLETED':
        message_content = f"The buyer has confirmed fulfillment for order #{instance.id}."
        notification_recipient = seller # Notify the seller of the completion

    # If there's a message to send, send it and trigger the navbar notification
    if conversation and message_content and notification_recipient:
        send_system_message(conversation, message_content, buyer)
        async_to_sync(send_message_notification)(notification_recipient)

    # Always send order count updates to both users
    async_to_sync(send_order_update_notification)(buyer)
    async_to_sync(send_order_update_notification)(seller)


@receiver(post_save, sender=Review)
def review_creation_message(sender, instance, created, **kwargs):
    if created:
        order = instance.order
        buyer = order.buyer
        seller = order.seller
        
        conversation = Conversation.objects.filter(
            (Q(participant1=buyer) & Q(participant2=seller)) |
            (Q(participant1=seller) & Q(participant2=buyer))
        ).first()

        if conversation:
            message_content = f"The buyer has left a {instance.rating}-star review."
            # Send the system message in the chat
            send_system_message(conversation, message_content, buyer)
            # Send the navbar notification to the seller
            async_to_sync(send_message_notification)(seller)