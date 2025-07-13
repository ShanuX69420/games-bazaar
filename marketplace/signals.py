# marketplace/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q
from .models import Order, Review, Conversation, Message

def send_system_message(conversation, content):
    system_message = Message.objects.create(
        conversation=conversation,
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
            'timestamp': str(system_message.timestamp.strftime("%b. %d, %Y, %I:%M %p")),
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

    # This is the new, more detailed message for a new order
    if created and instance.status == 'PROCESSING':
        message_content = (
            f"The buyer {instance.buyer.username} has paid for order #{instance.id}. "
            f"{instance.product.game.title} - {instance.product.listing_title}\n\n"
            f"{instance.buyer.username}, do not forget to press the «Confirm order fulfillment» button once you finish."
        )
        send_system_message(conversation, message_content)
        
    elif not created and instance.status == 'COMPLETED' and instance.tracker.has_changed('status'):
        message_content = f"The buyer has confirmed fulfillment for order #{instance.id} and the seller {instance.seller.username} has been paid."
        send_system_message(conversation, message_content)

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
            send_system_message(conversation, message_content)