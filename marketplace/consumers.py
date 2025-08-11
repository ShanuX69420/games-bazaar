# marketplace/consumers.py

import json
import asyncio
import logging
from datetime import timedelta
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import Q
from django.db import models
from django.utils import timezone
from .models import Conversation, Message, Profile
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Security logging
security_logger = logging.getLogger('security.websocket')


# --- Database Functions ---

@database_sync_to_async
def update_user_last_seen(user):
    """
    Safely updates the last_seen field and resets offline broadcast tracking.
    """
    if user.is_authenticated:
        Profile.objects.filter(user=user).update(
            last_seen=timezone.now(),
            offline_broadcast_at=None  # Reset so they can be broadcasted as offline again later
        )

@database_sync_to_async
def get_unread_conversation_count(user):
    """
    Calculates the number of conversations with at least one unread message for a user.
    Optimized to use a single query instead of subquery.
    """
    if not user.is_authenticated:
        return 0
    
    return Message.objects.filter(
        Q(conversation__participant1=user) | Q(conversation__participant2=user) | Q(conversation__moderator=user),
        is_read=False
    ).exclude(
        sender=user
    ).values('conversation').distinct().count()

@database_sync_to_async
def mark_message_as_read_in_db(message_id, user):
    """
    Marks a specific message as read in the database and returns the message object.
    Ensures the user receiving the message is the one marking it as read.
    """
    try:
        message = Message.objects.select_related('conversation__participant1', 'conversation__participant2').get(id=message_id)
        
        # Security check: Make sure the user is a participant (including moderator) and not the sender
        is_participant = message.conversation.is_participant(user)
        if is_participant and message.sender != user and not message.is_read:
            message.is_read = True
            message.save(update_fields=['is_read'])
            return message
        return None # Return None if no update was needed
    except Message.DoesNotExist:
        return None

# --- Notification and Presence Functions ---

async def broadcast_presence(user, status_data, channel_layer):
    """
    Broadcasts a user's online status to all their conversation partners.
    This version is optimized to avoid instantiating Conversation objects.
    """
    @database_sync_to_async
    def get_participant_usernames(u):
        # Get conversations where the user is participant1
        p1_convs = Conversation.objects.filter(participant1=u).values_list('participant2__username', flat=True)
        # Get conversations where the user is participant2
        p2_convs = Conversation.objects.filter(participant2=u).values_list('participant1__username', flat=True)
        # Get conversations where the user is a moderator
        mod_convs_p1 = Conversation.objects.filter(moderator=u).values_list('participant1__username', flat=True)
        mod_convs_p2 = Conversation.objects.filter(moderator=u).values_list('participant2__username', flat=True)
        
        # Combine all unique usernames into a set
        all_participants = set(p1_convs) | set(p2_convs) | set(mod_convs_p1) | set(mod_convs_p2)
        
        return all_participants

    # Get the unique set of usernames to notify
    participant_usernames = await get_participant_usernames(user)

    # Broadcast the presence update to each unique participant
    for username in participant_usernames:
        if username != user.username: # Ensure we don't notify the user themselves
            await channel_layer.group_send(
                f"notifications_{username}",
                {
                    'type': 'send_notification',
                    'notification_type': 'presence_update',
                    'data': status_data
                }
            )

async def notify_read_receipt(message, user, channel_layer):
    """
    Sends a notification to update the unread message count after a message is read.
    """
    unread_count = await get_unread_conversation_count(user)
    await channel_layer.group_send(
        f"notifications_{user.username}",
        {
            "type": "send_notification",
            "notification_type": "read_receipt_update",
            "data": {
                'unread_conversations_count': unread_count,
                'conversation_id': message.conversation.id
            },
        }
    )

# --- Offline User Checking ---

@database_sync_to_async
def get_recently_offline_users():
    """Get users who should be marked offline (last seen > 5 minutes ago)
    but haven't been broadcasted as offline recently"""
    five_minutes_ago = timezone.now() - timedelta(minutes=5)
    one_minute_ago = timezone.now() - timedelta(minutes=1)
    
    # Get users who:
    # 1. Have last_seen older than 5 minutes (should be offline)
    # 2. Either have no offline_broadcast_at OR it was more than 1 minute ago
    recently_offline = Profile.objects.filter(
        last_seen__isnull=False,
        last_seen__lt=five_minutes_ago
    ).filter(
        # Only broadcast if we haven't done it recently
        models.Q(offline_broadcast_at__isnull=True) | 
        models.Q(offline_broadcast_at__lt=one_minute_ago)
    ).select_related('user')
    
    return list(recently_offline)

async def broadcast_offline_status_for_user(user, channel_layer):
    """Broadcast offline status for a specific user to their conversation partners"""
    @database_sync_to_async
    def get_participant_usernames(u):
        # Get conversations where the user is participant1
        p1_convs = Conversation.objects.filter(participant1=u).values_list('participant2__username', flat=True)
        # Get conversations where the user is participant2
        p2_convs = Conversation.objects.filter(participant2=u).values_list('participant1__username', flat=True)
        # Get conversations where the user is a moderator
        mod_convs_p1 = Conversation.objects.filter(moderator=u).values_list('participant1__username', flat=True)
        mod_convs_p2 = Conversation.objects.filter(moderator=u).values_list('participant2__username', flat=True)
        
        # Combine all unique usernames into a set
        all_participants = set(p1_convs) | set(p2_convs) | set(mod_convs_p1) | set(mod_convs_p2)
        
        return all_participants
    
    @database_sync_to_async
    def mark_offline_broadcasted(u):
        """Mark that we've broadcasted this user's offline status"""
        Profile.objects.filter(user=u).update(offline_broadcast_at=timezone.now())

    # Get the unique set of usernames to notify
    participant_usernames = await get_participant_usernames(user)

    # Broadcast the offline status to each unique participant
    for username in participant_usernames:
        if username != user.username:
            await channel_layer.group_send(
                f"notifications_{username}",
                {
                    'type': 'send_notification',
                    'notification_type': 'presence_update',
                    'data': {
                        'username': user.username,
                        'is_online': False,
                        'last_seen_iso': user.profile.last_seen.isoformat() if user.profile.last_seen else None
                    }
                }
            )
    
    # Mark that we've broadcasted this user's offline status
    await mark_offline_broadcasted(user)

# --- Offline Status Checking ---

# --- Main Consumers ---

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return

        other_user_username = self.scope['url_route']['kwargs']['username']
        self.other_user = await self.get_user(other_user_username)

        if not self.other_user:
            # Log suspicious activity - trying to connect to non-existent user
            security_logger.warning(
                f"WebSocket connection attempt to non-existent user '{other_user_username}' by {self.user.username} "
                f"from {self.scope.get('client', ['unknown'])[0]}"
            )
            await self.close()
            return

        # SECURITY: Enhanced authorization checks to prevent unauthorized access
        # 1. Check if conversation exists and user is authorized
        self.conversation = await self.get_existing_conversation(self.user, self.other_user)
        if not self.conversation:
            # Log unauthorized access attempt - no existing conversation
            security_logger.warning(
                f"Unauthorized WebSocket connection attempt by {self.user.username} to chat with {other_user_username} "
                f"(no existing conversation) from {self.scope.get('client', ['unknown'])[0]}"
            )
            await self.close()
            return

        # 2. Verify user is a legitimate participant (including moderator support)
        if not await self.is_user_participant(self.conversation, self.user):
            # Log critical security violation - trying to access conversation they're not part of
            security_logger.error(
                f"CRITICAL: User {self.user.username} attempted to access conversation {self.conversation.id} "
                f"where they are not a participant from {self.scope.get('client', ['unknown'])[0]}"
            )
            await self.close()
            return

        # 3. Additional business logic authorization: verify user can access this conversation
        # This prevents users from connecting to conversations they shouldn't see
        if not await self.user_has_conversation_access(self.user, self.conversation):
            # Log authorization failure
            security_logger.error(
                f"CRITICAL: User {self.user.username} failed business logic authorization for conversation "
                f"{self.conversation.id} from {self.scope.get('client', ['unknown'])[0]}"
            )
            await self.close()
            return

        self.room_group_name = f'chat_{self.conversation.id}'

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Mark messages as read upon connection
        await self.mark_messages_as_read(self.conversation, self.user)

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name') and self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Handles inbound events from the client, like "mark as read".
        """
        try:
            data = json.loads(text_data)
            event_type = data.get('type')

            if event_type == 'mark_as_read' and self.user.is_authenticated:
                message_id = data.get('message_id')
                if message_id:
                    updated_message = await mark_message_as_read_in_db(message_id, self.user)
                    if updated_message:
                        # Send read receipt notification to update UI
                        unread_count = await get_unread_conversation_count(self.user)
                        await self.channel_layer.group_send(
                            f"notifications_{self.user.username}",
                            {
                                "type": "send_notification",
                                "notification_type": "read_receipt_update",
                                "data": {
                                    'unread_conversations_count': unread_count,
                                    'conversation_id': updated_message.conversation.id
                                },
                            }
                        )
            
            elif event_type == 'mark_conversation_as_read' and self.user.is_authenticated:
                # Mark all unread messages in this conversation as read (when user returns to tab)
                await self.mark_messages_as_read(self.conversation, self.user)
                
            elif event_type == 'ping':
                # Handle heartbeat ping - respond with pong
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))

        except Exception as e:
            # It's good practice to log errors, even if we don't crash the consumer.
            print(f"ChatConsumer receive error: {e}")

    async def chat_message(self, event):
        """
        Receives a message from a channel layer group (sent by a signal)
        and forwards it to the client's WebSocket.
        """
        message_html = event.get('message_html')
        message_id = event.get('message_id')
        
        # Don't auto-mark messages as read here - let the client decide
        # based on page visibility. This allows proper notifications when
        # the tab is not active or browser is minimized
        
        # The event now contains the pre-rendered HTML, which we forward directly.
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'message_html': message_html,
            'message_id': message_id
        }))

    # --- Helper Methods for ChatConsumer ---

    @database_sync_to_async
    def get_user(self, username):
        from django.contrib.auth.models import User
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_existing_conversation(self, user1, user2):
        """
        Get an existing conversation between two users (doesn't create new ones).
        Returns None if no conversation exists.
        """
        # Canonical ordering for participants to prevent duplicate conversations
        if user1.id > user2.id:
            user1, user2 = user2, user1
        try:
            return Conversation.objects.get(participant1=user1, participant2=user2)
        except Conversation.DoesNotExist:
            return None

    @database_sync_to_async
    def is_user_participant(self, conversation, user):
        """
        Verify that the user is a legitimate participant in the conversation.
        """
        return conversation.is_participant(user)

    @database_sync_to_async
    def user_has_conversation_access(self, user, conversation):
        """
        Enhanced authorization check: Verify the user has legitimate business reason 
        to access this conversation. This prevents unauthorized connection attempts.
        
        A user has access if they are:
        1. participant1 or participant2 of the conversation
        2. A moderator assigned to the conversation
        3. Staff/superuser (for admin purposes)
        """
        # Allow staff/superuser access for moderation purposes
        if user.is_staff or user.is_superuser:
            return True
            
        # Check if user is one of the direct participants
        if user == conversation.participant1 or user == conversation.participant2:
            return True
            
        # Check if user is assigned as a moderator for this conversation
        if conversation.moderator and user == conversation.moderator:
            return True
            
        # If none of the above, deny access
        return False

    @database_sync_to_async
    def get_or_create_conversation(self, user1, user2):
        # Canonical ordering for participants to prevent duplicate conversations
        if user1.id > user2.id:
            user1, user2 = user2, user1
        conversation, created = Conversation.objects.get_or_create(participant1=user1, participant2=user2)
        return conversation

    async def mark_messages_as_read(self, conversation, user):
        """Marks all messages in the conversation as read when it's opened by the recipient."""
        # Batch update for better performance
        @database_sync_to_async
        def batch_update_messages():
            return conversation.messages.filter(is_read=False).exclude(sender=user).update(is_read=True)
        
        updated_count = await batch_update_messages()

        # If any messages were updated, we need to send a notification
        if updated_count > 0:
            # Get the last message efficiently
            @database_sync_to_async
            def get_last_message():
                return conversation.messages.select_related('conversation').last()
            
            last_message = await get_last_message()
            if last_message:
                await notify_read_receipt(last_message, user, self.channel_layer)


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        
        self.room_group_name = f"notifications_{self.user.username}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        
        # Update presence on connection
        await update_user_last_seen(self.user)
        await broadcast_presence(self.user, {
            'username': self.user.username,
            'is_online': True,
            'last_seen_iso': timezone.now().isoformat()
        }, self.channel_layer)
        
        # Check for recently offline users on connection
        recently_offline = await get_recently_offline_users()
        for profile in recently_offline:
            await broadcast_offline_status_for_user(profile.user, self.channel_layer)

    async def disconnect(self, close_code):
        if hasattr(self, 'user') and self.user.is_authenticated:
            # Update last_seen on disconnect
            await update_user_last_seen(self.user)
            
            # Note: We don't broadcast offline status immediately anymore
            # Users will appear offline after 5 minutes of inactivity
            
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Handles heartbeat pings from the client to update the user's online status.
        """
        try:
            data = json.loads(text_data)
            if data.get('type') == 'heartbeat':
                # Update last_seen timestamp
                await update_user_last_seen(self.user)
                
                # Broadcast current online status to conversation partners
                await broadcast_presence(self.user, {
                    'username': self.user.username,
                    'is_online': True,
                    'last_seen_iso': timezone.now().isoformat()
                }, self.channel_layer)
                
                # Check for recently offline users and broadcast their status
                recently_offline = await get_recently_offline_users()
                for profile in recently_offline:
                    await broadcast_offline_status_for_user(profile.user, self.channel_layer)
                
        except (json.JSONDecodeError, Exception) as e:
            print(f"WebSocket receive error for {self.user.username}: {e}")
            pass

    async def send_notification(self, event):
        """
        Sends a notification from the channel layer to the client's WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': event['notification_type'],
            'data': event['data']
        }))