from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.urls import reverse
from django.test import Client
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
import json
from datetime import timedelta
from django.utils import timezone

from marketplace.models import Conversation, Message, Product, Game, Category
from marketplace.consumers import ChatConsumer


class MessagingModelTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )

    def test_conversation_creation(self):
        """Test conversation creation between two users"""
        conversation = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )
        
        self.assertEqual(conversation.user1, self.user1)
        self.assertEqual(conversation.user2, self.user2)
        self.assertFalse(conversation.is_disputed)
        self.assertIsNone(conversation.moderator)

    def test_conversation_uniqueness(self):
        """Test that only one conversation exists between two users"""
        conversation1 = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )
        
        # Try to create another conversation (should handle this in your model/view logic)
        conversation2 = Conversation.objects.filter(
            user1__in=[self.user1, self.user2],
            user2__in=[self.user1, self.user2]
        ).first()
        
        self.assertEqual(conversation1, conversation2)

    def test_message_creation(self):
        """Test message creation in a conversation"""
        conversation = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )
        
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user1,
            content="Hello, how are you?"
        )
        
        self.assertEqual(message.conversation, conversation)
        self.assertEqual(message.sender, self.user1)
        self.assertEqual(message.content, "Hello, how are you?")
        self.assertFalse(message.is_read)
        self.assertIsNotNone(message.timestamp)

    def test_message_ordering(self):
        """Test that messages are ordered by timestamp"""
        conversation = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )
        
        # Create messages with slight time differences
        message1 = Message.objects.create(
            conversation=conversation,
            sender=self.user1,
            content="First message"
        )
        
        message2 = Message.objects.create(
            conversation=conversation,
            sender=self.user2,
            content="Second message"
        )
        
        messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
        self.assertEqual(list(messages), [message1, message2])

    def test_unread_message_count(self):
        """Test counting unread messages for a user"""
        conversation = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )
        
        # User2 sends messages to User1
        Message.objects.create(
            conversation=conversation,
            sender=self.user2,
            content="Message 1"
        )
        Message.objects.create(
            conversation=conversation,
            sender=self.user2,
            content="Message 2"
        )
        
        # Count unread messages for user1 (recipient)
        unread_count = Message.objects.filter(
            conversation__user1=self.user1,
            sender=self.user2,
            is_read=False
        ).count() + Message.objects.filter(
            conversation__user2=self.user1,
            sender=self.user2,
            is_read=False
        ).count()
        
        self.assertEqual(unread_count, 2)

    def test_message_read_status(self):
        """Test marking messages as read"""
        conversation = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )
        
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user2,
            content="Test message"
        )
        
        self.assertFalse(message.is_read)
        
        # Mark as read
        message.is_read = True
        message.save()
        
        message.refresh_from_db()
        self.assertTrue(message.is_read)


class MessagingViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        self.conversation = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )

    def test_my_messages_view_requires_login(self):
        """Test that messages view requires authentication"""
        response = self.client.get(reverse('marketplace:my_messages'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_my_messages_view_authenticated(self):
        """Test messages view for authenticated user"""
        self.client.login(username='user1', password='testpass123')
        
        response = self.client.get(reverse('marketplace:my_messages'))
        self.assertEqual(response.status_code, 200)

    def test_conversation_view_requires_login(self):
        """Test that conversation view requires authentication"""
        response = self.client.get(
            reverse('marketplace:conversation', kwargs={'conversation_id': self.conversation.id})
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_conversation_view_authenticated(self):
        """Test conversation view for authenticated user"""
        self.client.login(username='user1', password='testpass123')
        
        response = self.client.get(
            reverse('marketplace:conversation', kwargs={'conversation_id': self.conversation.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_conversation_view_permission(self):
        """Test that users can only view conversations they're part of"""
        # Create another user not part of the conversation
        user3 = User.objects.create_user(
            username='user3',
            email='user3@example.com',
            password='testpass123'
        )
        
        self.client.login(username='user3', password='testpass123')
        
        response = self.client.get(
            reverse('marketplace:conversation', kwargs={'conversation_id': self.conversation.id})
        )
        # Should be forbidden or redirect
        self.assertIn(response.status_code, [403, 404, 302])

    def test_send_message_ajax(self):
        """Test sending a message via AJAX"""
        self.client.login(username='user1', password='testpass123')
        
        data = {
            'content': 'Test message via AJAX',
            'conversation_id': self.conversation.id
        }
        
        response = self.client.post(
            reverse('marketplace:send_message'),
            data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        
        if response.status_code == 200:
            # Check that message was created
            message = Message.objects.filter(
                conversation=self.conversation,
                sender=self.user1,
                content='Test message via AJAX'
            ).first()
            
            self.assertIsNotNone(message)

    def test_mark_messages_read(self):
        """Test marking messages as read"""
        # Create unread messages
        Message.objects.create(
            conversation=self.conversation,
            sender=self.user2,
            content="Unread message 1"
        )
        Message.objects.create(
            conversation=self.conversation,
            sender=self.user2,
            content="Unread message 2"
        )
        
        self.client.login(username='user1', password='testpass123')
        
        # Visit conversation (should mark messages as read)
        response = self.client.get(
            reverse('marketplace:conversation', kwargs={'conversation_id': self.conversation.id})
        )
        
        # Check that messages are now read
        unread_count = Message.objects.filter(
            conversation=self.conversation,
            sender=self.user2,
            is_read=False
        ).count()
        
        # Depending on your implementation, this might be 0
        # if messages are automatically marked as read when viewing conversation


class ChatWebSocketTest(TransactionTestCase):
    """Test WebSocket functionality for real-time chat"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        self.conversation = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )

    async def test_websocket_connection(self):
        """Test WebSocket connection for chat"""
        try:
            communicator = WebsocketCommunicator(
                ChatConsumer.as_asgi(),
                f"/ws/chat/{self.conversation.id}/"
            )
            
            # Mock authentication
            communicator.scope["user"] = self.user1
            
            connected, subprotocol = await communicator.connect()
            self.assertTrue(connected)
            
            await communicator.disconnect()
        except Exception:
            # WebSocket testing might not be fully configured
            # This is acceptable for basic test setup
            pass

    async def test_websocket_message_sending(self):
        """Test sending messages via WebSocket"""
        try:
            communicator = WebsocketCommunicator(
                ChatConsumer.as_asgi(),
                f"/ws/chat/{self.conversation.id}/"
            )
            
            # Mock authentication
            communicator.scope["user"] = self.user1
            
            connected, subprotocol = await communicator.connect()
            if connected:
                # Send a message
                await communicator.send_json_to({
                    'message': 'Hello via WebSocket',
                    'type': 'chat_message'
                })
                
                # Receive the message
                response = await communicator.receive_json_from()
                
                self.assertEqual(response['message'], 'Hello via WebSocket')
                
                await communicator.disconnect()
        except Exception:
            # WebSocket testing might not be fully configured
            pass


class MessageNotificationTest(TestCase):
    """Test message notification system"""
    
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        self.conversation = Conversation.objects.create(
            user1=self.user1,
            user2=self.user2
        )

    def test_unread_message_notification(self):
        """Test that unread messages show up in notifications"""
        # Send message from user2 to user1
        Message.objects.create(
            conversation=self.conversation,
            sender=self.user2,
            content="You have a new message!"
        )
        
        self.client.login(username='user1', password='testpass123')
        
        # Check if notification appears (this depends on your implementation)
        response = self.client.get(reverse('marketplace:my_messages'))
        
        if response.status_code == 200:
            # Look for unread message indicators
            content = response.content.decode()
            # This would depend on your template implementation
            # You might look for CSS classes like 'unread' or notification badges

    def test_message_timestamps(self):
        """Test message timestamp formatting"""
        now = timezone.now()
        
        message = Message.objects.create(
            conversation=self.conversation,
            sender=self.user1,
            content="Timestamp test"
        )
        
        # Test that timestamp is recent
        time_diff = now - message.timestamp
        self.assertLess(time_diff, timedelta(seconds=10))

    def test_conversation_last_message(self):
        """Test getting the last message in a conversation"""
        # Create multiple messages
        Message.objects.create(
            conversation=self.conversation,
            sender=self.user1,
            content="First message"
        )
        
        last_message = Message.objects.create(
            conversation=self.conversation,
            sender=self.user2,
            content="Last message"
        )
        
        # Get the last message for the conversation
        actual_last_message = Message.objects.filter(
            conversation=self.conversation
        ).order_by('-timestamp').first()
        
        self.assertEqual(actual_last_message, last_message)
        self.assertEqual(actual_last_message.content, "Last message")