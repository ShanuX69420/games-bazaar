# marketplace/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q
from .models import Order, Review, Conversation, Message

# This function now correctly accepts a sender_user
def send_system_message(conversation, content, sender_user):
    system_message = Message.objects.create(
        conversation=conversation,
        sender=sender_user, # Assign the sender
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
    conversation = Conversation.objects.filter(
        (Q(participant1=instance.buyer) & Q(participant2=instance.seller)) |
        (Q(participant1=instance.seller) & Q(participant2=instance.buyer))
    ).first()

    if not conversation: return

    if created and instance.status == 'PROCESSING':
        message_content = f"The buyer, {instance.buyer.username}, has paid for order #{instance.id} ({instance.product.listing_title})."
        # Pass the buyer as the sender of the system event
        send_system_message(conversation, message_content, instance.buyer)

    elif not created and hasattr(instance, 'tracker') and instance.tracker.has_changed('status') and instance.status == 'COMPLETED':
        message_content = f"The buyer has confirmed fulfillment for order #{instance.id}."
        send_system_message(conversation, message_content, instance.buyer)

@receiver(post_save, sender=Review)
def review_creation_message(sender, instance, created, **kwargs):
    if created:
        order = instance.order
        conversation = Conversation.objects.filter(
            (Q(participant1=order.buyer) & Q(participant2=order.seller)) |
            (Q(participant1=order.seller) & Q(participant2=order.buyer))
        ).first()
        if conversation:
            message_content = f"The buyer has left a {instance.rating}-star review."
            # Pass the buyer as the sender of the system event
            send_system_message(conversation, message_content, instance.buyer)