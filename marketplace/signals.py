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

@database_sync_to_async
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
    """Creates a system message in a chat."""
    system_message = Message.objects.create(
        conversation=conversation,
        sender=sender_user,
        content=content,
        is_system_message=True
    )
    channel_layer = get_channel_layer()
    room_group_name = f'chat_{conversation.id}'
    
    # Send the message to the chat window
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
    return system_message

# --- NEW: Signal handler for when a new message is saved ---

@receiver(post_save, sender=Message)
def new_message_handler(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        conversation = instance.conversation
        
        # Notify both participants in the conversation
        for user in [conversation.participant1, conversation.participant2]:
            user_context = async_to_sync(get_user_context)(user)
            notification_group_name = f'notifications_{user.username}'
            
            async_to_sync(channel_layer.group_send)(
                notification_group_name,
                {
                    "type": "send_notification",
                    "notification_type": "new_message",
                    "data": {
                        'unread_conversations_count': user_context['unread_conversations_count'],
                        'conversation_id': conversation.id,
                        'last_message_content': instance.content,
                        'last_message_timestamp': str(instance.timestamp.isoformat()),
                        'sender_username': instance.sender.username,
                    },
                }
            )

# --- REBUILT: Signal handler for Orders (The Core of the fix) ---

@receiver(post_save, sender=Order)
def order_status_change_handler(sender, instance, created, **kwargs):
    """
    Handles all logic when an order is created or its status changes.
    This now sends fully rendered HTML partials for real-time updates.
    """
    channel_layer = get_channel_layer()
    buyer = instance.buyer
    seller = instance.seller
    conversation = Conversation.objects.filter(
        (Q(participant1=buyer) & Q(participant2=seller)) |
        (Q(participant1=seller) & Q(participant2=buyer))
    ).first()

    # --- When a new order is created and paid for ---
    if created and instance.status == 'PROCESSING':
        # Create transactions for both users
        buyer_tx = Transaction.objects.create(
            user=buyer, amount=-instance.total_price, transaction_type='ORDER_PURCHASE',
            status='COMPLETED', description=f"Purchase of '{instance.product.listing_title}'", order=instance
        )
        seller_tx = Transaction.objects.create(
            user=seller, amount=instance.total_price, transaction_type='ORDER_SALE',
            status='PROCESSING', description=f"Sale of '{instance.product.listing_title}'", order=instance
        )

        # Notify the seller about the new sale
        if seller.is_authenticated:
            # Get the latest notification counts for the seller
            seller_context = async_to_sync(get_user_context)(seller)
            # Render the HTML for the new rows
            sale_row_html = render_to_string('marketplace/partials/sale_row.html', {'order': instance})
            dashboard_row_html = render_to_string('marketplace/partials/dashboard_order_row.html', {'order': instance})
            transaction_row_html = render_to_string('marketplace/partials/transaction_row.html', {'tx': seller_tx})

            # Send the complete payload via WebSocket
            async_to_sync(channel_layer.group_send)(
                f'notifications_{seller.username}', {
                    'type': 'send_notification',
                    'notification_type': 'new_sale_update',
                    'data': {
                        'counts': seller_context,
                        'sale_row_html': sale_row_html,
                        'dashboard_row_html': dashboard_row_html,
                        'transaction_row_html': transaction_row_html
                    }
                }
            )

        # Notify the buyer about their new purchase
        if buyer.is_authenticated:
            buyer_context = async_to_sync(get_user_context)(buyer)
            # You would create purchase_row_html and transaction_row_html here if you had a "My Purchases" page to update in real-time
            
            async_to_sync(channel_layer.group_send)(
                f'notifications_{buyer.username}', {
                    'type': 'send_notification',
                    'notification_type': 'new_purchase_update',
                    'data': { 'counts': buyer_context }
                }
            )

        # Send a system message to the chat
        if conversation:
            send_system_message(conversation, f"The buyer, {buyer.username}, has paid for order #{instance.id} ({instance.product.listing_title}).", buyer)

    # --- When an order is marked as COMPLETED by the buyer ---
    elif not created and instance.tracker.has_changed('status') and instance.status == 'COMPLETED':
        # Finalize the seller's transaction
        net_earning = instance.total_price - (instance.commission_paid or 0)
        Transaction.objects.filter(order=instance, user=seller).update(status='COMPLETED', amount=net_earning)

        # Send notifications to update counts for both users
        for user in [buyer, seller]:
            if user.is_authenticated:
                user_context = async_to_sync(get_user_context)(user)
                async_to_sync(channel_layer.group_send)(
                    f'notifications_{user.username}', {
                        'type': 'send_notification',
                        'notification_type': 'order_completed_update',
                        'data': { 'counts': user_context }
                    }
                )
        
        # Send system message
        if conversation:
            send_system_message(conversation, f"The buyer has confirmed fulfillment for order #{instance.id}.", buyer)

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