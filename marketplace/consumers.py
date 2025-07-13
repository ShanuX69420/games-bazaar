import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Conversation, Message

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        other_user_username = self.scope['url_route']['kwargs']['username']
        self.user = self.scope['user']

        # This ensures room_group_name always exists
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
        # Only try to discard if the user successfully joined a room
        if self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_content = text_data_json['message']
        new_message = await self.create_message(self.conversation, self.user, message_content)
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': new_message.content,
                'sender': self.user.username,
                'timestamp': str(new_message.timestamp.strftime("%b. %d, %Y, %I:%M %p"))
            }
        )

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
        conversation.save()
        return conversation

    @database_sync_to_async
    def create_message(self, conversation, sender, content):
        message = Message.objects.create(conversation=conversation, sender=sender, content=content)
        conversation.save()
        return message

    @database_sync_to_async
    def mark_messages_as_read(self, conversation, user):
        conversation.messages.filter(is_read=False).exclude(sender=user).update(is_read=True)