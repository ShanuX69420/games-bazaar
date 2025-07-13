import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Conversation, Message

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        other_user_username = self.scope['url_route']['kwargs']['username']
        self.user = self.scope['user']
        self.room_group_name = None 
        if not self.user.is_authenticated:
            await self.close(); return
        self.other_user = await self.get_user(other_user_username)
        if not self.other_user:
            await self.close(); return
        self.conversation = await self.get_or_create_conversation(self.user, self.other_user)
        self.room_group_name = f'chat_{self.conversation.id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.mark_messages_as_read(self.conversation, self.user)

    async def disconnect(self, close_code):
        if self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_content = text_data_json['message']
            if not message_content.strip():
                return

            new_message = await self.create_message(self.conversation, self.user, message_content)
            
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': new_message.content,
                    'sender': self.user.username,
                    'timestamp': str(new_message.timestamp.isoformat())
                }
            )

            # --- MODIFIED LOGIC ---
            # We now get the count of unread conversations and send it.
            unread_convo_count = await self.get_unread_conversation_count(self.other_user)
            notification_group_name = f'notifications_{self.other_user.username}'
            await self.channel_layer.group_send(
                notification_group_name,
                {
                    'type': 'send_notification',
                    'notification_type': 'new_message',
                    'data': {'unread_conversations_count': unread_convo_count}
                }
            )
            # --- END MODIFIED LOGIC ---

        except Exception as e:
            print(f"!!! CHATCONSUMER ERROR in receive method: {e} !!!")


    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'timestamp': event['timestamp']
        }))

    @database_sync_to_async
    def get_user(self, username):
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_conversation(self, user1, user2):
        if user1.id > user2.id:
            user1, user2 = user2, user1
        conversation, created = Conversation.objects.get_or_create(participant1=user1, participant2=user2)
        return conversation

    @database_sync_to_async
    def create_message(self, conversation, sender, content):
        message = Message.objects.create(conversation=conversation, sender=sender, content=content)
        conversation.save()
        return message

    @database_sync_to_async
    def mark_messages_as_read(self, conversation, user):
        conversation.messages.filter(is_read=False).exclude(sender=user).update(is_read=True)

    # --- NEW COUNTING FUNCTION ---
    @database_sync_to_async
    def get_unread_conversation_count(self, user):
        """Calculates the total number of conversations with unread messages for a user."""
        user_conversations = Conversation.objects.filter(Q(participant1=user) | Q(participant2=user))
        # Count the number of distinct conversations that have unread messages for this user.
        return Message.objects.filter(
            conversation__in=user_conversations,
            is_read=False
        ).exclude(
            sender=user
        ).values('conversation').distinct().count()


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            await self.close()
        else:
            self.room_group_name = f"notifications_{self.user.username}"
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()

    async def disconnect(self, close_code):
        if self.user.is_authenticated:
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def send_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': event['notification_type'],
            'data': event['data']
        }))