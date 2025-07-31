# marketplace/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone
from .models import Conversation, Message, Profile
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


# --- Database Functions ---

@database_sync_to_async
def update_user_last_seen(user):
    """
    Safely updates only the last_seen field for a user's profile.
    """
    if user.is_authenticated:
        Profile.objects.filter(user=user).update(last_seen=timezone.now())

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
            await self.close()
            return

        self.conversation = await self.get_or_create_conversation(self.user, self.other_user)
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
                        await notify_read_receipt(updated_message, self.user, self.channel_layer)

        except Exception as e:
            # It's good practice to log errors, even if we don't crash the consumer.
            print(f"ChatConsumer receive error: {e}")

    async def chat_message(self, event):
        """
        Receives a message from a channel layer group (sent by a signal)
        and forwards it to the client's WebSocket.
        """
        await self.send(text_data=json.dumps({
            'message_id': event.get('message_id'),
            'message': event.get('message'),
            'sender': event.get('sender'),
            'timestamp': event.get('timestamp'),
            'is_system_message': event.get('is_system_message', False),
            'image_url': event.get('image_url')
        }))

    # --- Helper Methods for ChatConsumer ---

    @database_sync_to_async
    def get_user(self, username):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

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
        
        # Update presence immediately on connection (important for Opera)
        await update_user_last_seen(self.user)
        await broadcast_presence(self.user, {
            'username': self.user.username,
            'is_online': True,
            'last_seen_iso': timezone.now().isoformat()
        }, self.channel_layer)
        
        # Log connection for debugging Opera issues
        print(f"User {self.user.username} connected to notifications at {timezone.now()}")

    async def disconnect(self, close_code):
        if hasattr(self, 'user') and self.user.is_authenticated:
            # Update last_seen immediately before disconnect
            await update_user_last_seen(self.user)
            
            # Broadcast offline status immediately
            await broadcast_presence(self.user, {
                'username': self.user.username,
                'is_online': False,
                'last_seen_iso': timezone.now().isoformat()
            }, self.channel_layer)

            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Listens for heartbeat pings from the client to update the user's online status.
        Enhanced for Opera browser stability.
        """
        try:
            data = json.loads(text_data)
            if data.get('type') == 'heartbeat':
                # Update last_seen with current timestamp
                await update_user_last_seen(self.user)
                
                # Broadcast online status to all conversation partners
                await broadcast_presence(self.user, {
                    'username': self.user.username,
                    'is_online': True,
                    'last_seen_iso': timezone.now().isoformat()
                }, self.channel_layer)
                
                # Send confirmation back to client for Opera debugging
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat_ack', 
                    'timestamp': timezone.now().isoformat(),
                    'user': self.user.username
                }))
                
        except (json.JSONDecodeError, Exception) as e:
            # Log errors for debugging but don't crash the connection
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