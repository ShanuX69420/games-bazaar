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
    """
    if not user.is_authenticated:
        return 0
    user_conversations = Conversation.objects.filter(Q(participant1=user) | Q(participant2=user))
    return Message.objects.filter(
        conversation__in=user_conversations,
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
        
        # Security check: Make sure the user is a participant and not the sender
        is_participant = (message.conversation.participant1 == user or message.conversation.participant2 == user)
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
    """
    # This must be an async function to get conversations
    @database_sync_to_async
    def get_conversations(u):
        return list(Conversation.objects.filter(Q(participant1=u) | Q(participant2=u)).select_related('participant1', 'participant2'))

    conversations = await get_conversations(user)

    for conv in conversations:
        other_user = conv.participant2 if conv.participant1 == user else conv.participant1
        await channel_layer.group_send(
            f"notifications_{other_user.username}",
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
        # This is now an async method, so we await the database call directly
        updated_count = await database_sync_to_async(
            conversation.messages.filter(is_read=False).exclude(sender=user).update
        )(is_read=True)

        # If any messages were updated, we need to send a notification
        if updated_count > 0:
            # We can now call our async helper directly
            await notify_read_receipt(conversation.messages.last(), user, self.channel_layer)


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
            return
        
        self.room_group_name = f"notifications_{self.user.username}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        
        await update_user_last_seen(self.user)
        await broadcast_presence(self.user, {
            'username': self.user.username,
            'is_online': True,
            'last_seen_iso': timezone.now().isoformat()
        }, self.channel_layer)

    async def disconnect(self, close_code):
        if hasattr(self, 'user') and self.user.is_authenticated:
            await update_user_last_seen(self.user)
            
            @database_sync_to_async
            def get_profile_last_seen_iso(u):
                try:
                    return Profile.objects.get(user=u).last_seen.isoformat()
                except (Profile.DoesNotExist, AttributeError):
                    return timezone.now().isoformat()

            last_seen_iso = await get_profile_last_seen_iso(self.user)
            
            await broadcast_presence(self.user, {
                'username': self.user.username,
                'is_online': False,
                'last_seen_iso': last_seen_iso
            }, self.channel_layer)

            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Listens for heartbeat pings from the client to update the user's online status.
        """
        try:
            data = json.loads(text_data)
            if data.get('type') == 'heartbeat':
                await update_user_last_seen(self.user)
                await broadcast_presence(self.user, {
                'username': self.user.username,
                'is_online': True,
                'last_seen_iso': timezone.now().isoformat()
            }, self.channel_layer)
        except (json.JSONDecodeError, Exception):
            # Ignore errors to keep the connection stable
            pass

    async def send_notification(self, event):
        """
        Sends a notification from the channel layer to the client's WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': event['notification_type'],
            'data': event['data']
        }))