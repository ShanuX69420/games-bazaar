# marketplace/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q
from .models import Order, Review, ReviewReply, Conversation, Message, Transaction, WithdrawalRequest, HeldFund
from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import reverse

# --- Helper functions ---

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

def send_system_message(conversation, message_type, order, user):
    """
    Creates and sends a formatted system message based on the event type.
    """
    content = ""
    if message_type == 'order_paid':
        content = (
            f'The buyer <a href="{reverse("public_profile", args=[order.buyer.username])}" class="fw-bold text-decoration-none">{order.buyer.username}</a> '
            f'has paid for order <a href="{reverse("order_detail", args=[order.clean_order_id])}" class="fw-bold text-decoration-none">{order.order_id}</a>. '
            f'Game: {order.game_snapshot.title}, Category: {order.category_snapshot.name}. '
            f'{order.listing_title_snapshot}\n'
            f'<a href="{reverse("public_profile", args=[order.buyer.username])}" class="fw-bold text-decoration-none">{order.buyer.username}</a>, '
            f'do not forget to press the "Confirm Order Fulfilment" button once you finish.'
        )
    elif message_type == 'order_confirmed':
        content = (
            f'The buyer <a href="{reverse("public_profile", args=[order.buyer.username])}" class="fw-bold text-decoration-none">{order.buyer.username}</a> '
            f'has confirmed that order <a href="{reverse("order_detail", args=[order.clean_order_id])}" class="fw-bold text-decoration-none">{order.order_id}</a> '
            f'has been fulfilled successfully and that the seller <a href="{reverse("public_profile", args=[order.seller.username])}" class="fw-bold text-decoration-none">{order.seller.username}</a> '
            f'has been paid.'
        )
    elif message_type == 'review_posted':
        content = (
            f'The buyer <a href="{reverse("public_profile", args=[order.buyer.username])}" class="fw-bold text-decoration-none">{order.buyer.username}</a> '
            f'has given feedback to the order <a href="{reverse("order_detail", args=[order.clean_order_id])}" class="fw-bold text-decoration-none">{order.order_id}</a>.'
        )
    elif message_type == 'review_replied':
        content = (
            f'The seller <a href="{reverse("public_profile", args=[order.seller.username])}" class="fw-bold text-decoration-none">{order.seller.username}</a> '
            f'has replied to their feedback to the order <a href="{reverse("order_detail", args=[order.clean_order_id])}" class="fw-bold text-decoration-none">{order.order_id}</a>.'
        )
    elif message_type == 'order_refunded':
        content = (
            f'The seller <a href="{reverse("public_profile", args=[order.seller.username])}" class="fw-bold text-decoration-none">{order.seller.username}</a> '
            f'has refunded order <a href="{reverse("order_detail", args=[order.clean_order_id])}" class="fw-bold text-decoration-none">{order.order_id}</a>. '
            f'The payment has been returned to your account.'
        )

    if content:
        Message.objects.create(
            conversation=conversation,
            sender=user,
            content=content,
            is_system_message=True
        )

# --- Signal Handlers ---

@receiver(post_save, sender=Message)
def new_message_handler(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        conversation = instance.conversation
        conversation.save() # Updates the `updated_at` field

        message_html = render_to_string(
            'marketplace/partials/message.html', 
            {'message': instance}
        )

        room_group_name = f'chat_{conversation.id}'

        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'chat_message',
                'message_html': message_html,
                'message_id': instance.id
            }
        )

        for user in [conversation.participant1, conversation.participant2]:
            if user:
                user_context = get_user_context(user)
                notification_group_name = f'notifications_{user.username}'
                # Invalidate cached navbar counters for this user so a quick refresh shows correct values
                cache.delete(f'user_notifications_{user.id}')
                
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

@receiver(post_save, sender=Order)
def order_status_change_handler(sender, instance, created, **kwargs):
    channel_layer = get_channel_layer()
    buyer = instance.buyer
    seller = instance.seller

    conversation = Conversation.objects.filter(
        (Q(participant1=buyer) & Q(participant2=seller)) |
        (Q(participant1=seller) & Q(participant2=buyer))
    ).first()

    if conversation:
        if created and instance.status in ['PROCESSING', 'DELIVERED']:
            send_system_message(conversation, 'order_paid', instance, buyer)
        elif not created and instance.tracker.has_changed('status') and instance.status == 'COMPLETED':
            send_system_message(conversation, 'order_confirmed', instance, buyer)
        elif not created and instance.tracker.has_changed('status') and instance.status == 'REFUNDED':
            send_system_message(conversation, 'order_refunded', instance, seller)

    if created or instance.tracker.has_changed('status'):
        status = instance.status
        if status == 'PROCESSING':
            if instance.amount_paid_from_balance > 0:
                Transaction.objects.update_or_create(
                    order=instance, user=buyer, transaction_type='ORDER_PURCHASE',
                    defaults={'amount': -instance.amount_paid_from_balance, 'status': 'COMPLETED', 'description': f"Balance payment for order {instance.order_id}"}
                )
            Transaction.objects.update_or_create(
                order=instance, user=seller, transaction_type='ORDER_SALE',
                defaults={'amount': instance.total_price, 'status': 'PROCESSING', 'description': f"Sale of '{instance.listing_title_snapshot}'"}
            )
        elif status == 'COMPLETED':
            Transaction.objects.filter(order=instance, user=buyer).update(status='COMPLETED')
            net_earning = instance.total_price - (instance.commission_paid or 0)
            Transaction.objects.filter(order=instance, user=seller).update(status='COMPLETED', amount=net_earning)
            if not seller.profile.is_verified_seller:
                HeldFund.objects.get_or_create(
                    user=seller,
                    order=instance,
                    defaults={'amount': net_earning}
                )
        elif status in ['CANCELLED', 'REFUNDED']:
            Transaction.objects.filter(order=instance).update(status=status)

    if instance.tracker.has_changed('status') or created:
        buyer_context = get_user_context(buyer)
        seller_context = get_user_context(seller)
        
        message_for_ui = f"New order {instance.order_id} from {buyer.username}." if created else f"Order {instance.order_id} status updated to {instance.get_status_display()}."

        for user, context, message in [(buyer, buyer_context, f"Your order {instance.order_id} status: {instance.get_status_display()}"), 
                                       (seller, seller_context, message_for_ui)]:
            if user:
                # Invalidate cached navbar counters for these users
                cache.delete(f'user_notifications_{user.id}')
                async_to_sync(channel_layer.group_send)(
                    f'notifications_{user.username}',
                    {
                        "type": "send_notification",
                        "notification_type": "order_update",
                        "data": {"message": message, **context}
                    }
                )

@receiver(post_save, sender=Review)
def review_creation_handler(sender, instance, created, **kwargs):
    if created:
        order = instance.order
        conversation = Conversation.objects.filter(
            (Q(participant1=order.buyer) & Q(participant2=order.seller)) |
            (Q(participant1=order.seller) & Q(participant2=order.buyer))
        ).first()

        if conversation:
            send_system_message(conversation, 'review_posted', order, order.buyer)

@receiver(post_save, sender=ReviewReply)
def review_reply_handler(sender, instance, created, **kwargs):
    if created:
        order = instance.review.order
        conversation = Conversation.objects.filter(
            (Q(participant1=order.buyer) & Q(participant2=order.seller)) |
            (Q(participant1=order.seller) & Q(participant2=order.buyer))
        ).first()

        if conversation:
            send_system_message(conversation, 'review_replied', order, order.seller)

@receiver(post_save, sender=WithdrawalRequest)
def withdrawal_transaction_handler(sender, instance, created, **kwargs):
    if created:
        # Only create a pending transaction record, don't show amount until approved
        Transaction.objects.create(
            user=instance.user, amount=0, transaction_type='WITHDRAWAL',
            status='PENDING', description=f'Withdrawal Request - {instance.get_payment_method_display()}', withdrawal=instance
        )
    else:
        # Handle status changes
        if instance.status == 'APPROVED':
            # Check if user has sufficient available balance and update transaction
            profile = instance.user.profile
            available_balance = profile.available_balance
            
            if available_balance >= instance.amount:
                # Update the transaction to show the actual withdrawal amount
                Transaction.objects.filter(withdrawal=instance).update(
                    status='COMPLETED', 
                    amount=-instance.amount,
                    description=f'Withdrawal - {instance.get_payment_method_display()} - {instance.account_title}'
                )
                
                # Clear the user's balance cache so it recalculates
                from django.core.cache import cache
                cache.delete(f'user_balance_{instance.user.id}')
                cache.delete(f'user_held_balance_{instance.user.id}')
            else:
                # If insufficient balance, reject the withdrawal
                instance.status = 'REJECTED'
                instance.admin_notes = f'Insufficient available balance at the time of approval. Available: Rs{available_balance:.2f}, Requested: Rs{instance.amount:.2f}'
                instance.save(update_fields=['status', 'admin_notes'])  # Prevent signal recursion
                Transaction.objects.filter(withdrawal=instance).update(
                    status='CANCELLED',
                    description='Withdrawal Cancelled - Insufficient Balance'
                )
        elif instance.status == 'REJECTED':
            Transaction.objects.filter(withdrawal=instance).update(
                status='CANCELLED',
                description='Withdrawal Request Rejected'
            )
