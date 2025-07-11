# marketplace/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import Order, ChatMessage, User
from channels.db import database_sync_to_async

class ChatConsumer(AsyncWebsocketConsumer):
    # This function runs when a user tries to connect
    async def connect(self):
        # Get the order ID from the URL
        self.order_id = self.scope['url_route']['kwargs']['order_id']
        self.room_group_name = f'chat_{self.order_id}'
        self.user = self.scope['user']

        # Check if the user has permission to join this chat
        if await self.is_user_part_of_order(self.user, self.order_id):
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
        else:
            # Reject the connection if the user is not the buyer or seller
            await self.close()

    # This function runs when a user disconnects
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # This function runs when the server receives a message from the WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_content = text_data_json['message']

        # Save the message to the database
        new_message = await self.save_message(self.user, self.order_id, message_content)

        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message_content,
                'sender': self.user.username,
                'timestamp': str(new_message.timestamp.strftime("%b. %d, %Y, %I:%M %p"))
            }
        )

    # This function is called when a message needs to be sent to the group
    async def chat_message(self, event):
        # Send message back to the WebSocket (the browser)
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'timestamp': event['timestamp']
        }))

    # Helper function to check permissions (must interact with DB asynchronously)
    @database_sync_to_async
    def is_user_part_of_order(self, user, order_id):
        if not user.is_authenticated:
            return False
        try:
            order = Order.objects.get(pk=order_id)
            return user == order.buyer or user == order.seller
        except Order.DoesNotExist:
            return False

    # Helper function to save message to the database
    @database_sync_to_async
    def save_message(self, sender, order_id, message):
        order = Order.objects.get(pk=order_id)
        return ChatMessage.objects.create(sender=sender, order=order, message=message)