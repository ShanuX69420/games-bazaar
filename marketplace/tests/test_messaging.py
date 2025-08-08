"""
Messaging System Tests - Based on comprehensive manual testing
Tests chat functionality, real-time messaging, security
Matches manual Test 9: Chat Functionality
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from marketplace.models import Conversation, Message, BlockedUser


class MessagingSystemTest(TestCase):
    """Test core messaging functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'pass123')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'pass123')
        self.client.login(username='user1', password='pass123')

    def test_conversation_creation(self):
        """Test that conversations are created automatically"""
        # Send a message - should create conversation
        response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
            'message': 'Hello, this is a test message!'
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        
        # Conversation should be created
        conversation = Conversation.objects.filter(
            participant1=self.user1, participant2=self.user2
        ).first()
        if not conversation:
            conversation = Conversation.objects.filter(
                participant1=self.user2, participant2=self.user1
            ).first()
        
        self.assertIsNotNone(conversation)

    def test_message_sending(self):
        """Test sending messages between users"""
        message_text = 'This is a test message with special chars: àáâãäå'
        
        response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
            'message': message_text
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        
        # Message should be saved
        message = Message.objects.filter(
            sender=self.user1,
            content__contains='test message'
        ).first()
        
        self.assertIsNotNone(message)

    def test_empty_message_rejection(self):
        """Test that empty messages are rejected"""
        response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
            'message': ''
        })
        
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertIn('empty', data['message'].lower())

    def test_message_with_image_attachment(self):
        """Test sending messages with image attachments"""
        # Create a fake image
        image_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
        image_file = SimpleUploadedFile(
            'test_chat_image.png',
            image_content,
            content_type='image/png'
        )
        
        response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
            'message': 'Check out this image!',
            'image': image_file
        })
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        
        # Message with image should be saved
        message = Message.objects.filter(
            sender=self.user1,
            image__isnull=False
        ).first()
        
        self.assertIsNotNone(message)

    def test_message_rate_limiting(self):
        """Test that message rate limiting works"""
        # Send many messages quickly
        for i in range(35):  # More than the 30 per minute limit
            response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
                'message': f'Spam message {i}'
            })
            
            if i >= 30:  # Should start rate limiting
                self.assertEqual(response.status_code, 429)
                data = response.json()
                self.assertIn('slow down', data['message'].lower())
            else:
                self.assertEqual(response.status_code, 200)


class MessageSecurityTest(TestCase):
    """Test messaging security features"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'pass123')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'pass123')

    def test_xss_prevention_in_messages(self):
        """Test XSS prevention in message content"""
        self.client.login(username='user1', password='pass123')
        
        xss_message = '<script>alert("XSS in chat!")</script>'
        
        response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
            'message': xss_message
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Message should be sanitized
        message = Message.objects.filter(sender=self.user1).first()
        self.assertNotIn('<script>', message.content)
        self.assertIn('&lt;script&gt;', message.content)  # Should be escaped

    def test_message_authorization(self):
        """Test that users can't send messages as other users"""
        self.client.login(username='user1', password='pass123')
        
        # Try to send message to non-existent user
        response = self.client.post('/ajax/send-message/nonexistent_user/', {
            'message': 'This should fail'
        })
        
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_messaging_blocked(self):
        """Test that unauthenticated users cannot send messages"""
        # Don't log in
        response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
            'message': 'This should be blocked'
        })
        
        # Should redirect to login or return 403
        self.assertIn(response.status_code, [302, 403])


class BlockingSystemTest(TestCase):
    """Test user blocking functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'pass123')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'pass123')

    def test_user_blocking(self):
        """Test blocking another user"""
        self.client.login(username='user1', password='pass123')
        
        response = self.client.post(f'/ajax/block-user/{self.user2.id}/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Block relationship should be created
        block = BlockedUser.objects.filter(
            blocker=self.user1,
            blocked=self.user2
        ).first()
        
        self.assertIsNotNone(block)

    def test_blocked_user_cannot_send_messages(self):
        """Test that blocked users cannot send messages"""
        # Block user2
        BlockedUser.objects.create(blocker=self.user1, blocked=self.user2)
        
        # Try to send message as blocked user
        self.client.login(username='user2', password='pass123')
        response = self.client.post(f'/ajax/send-message/{self.user1.username}/', {
            'message': 'This should be blocked'
        })
        
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn('cannot send', data['message'].lower())

    def test_user_unblocking(self):
        """Test unblocking a user"""
        # First block the user
        BlockedUser.objects.create(blocker=self.user1, blocked=self.user2)
        
        self.client.login(username='user1', password='pass123')
        response = self.client.post(f'/ajax/unblock-user/{self.user2.id}/')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Block relationship should be removed
        block_exists = BlockedUser.objects.filter(
            blocker=self.user1,
            blocked=self.user2
        ).exists()
        
        self.assertFalse(block_exists)

    def test_mutual_blocking(self):
        """Test mutual blocking scenarios"""
        # Both users block each other
        BlockedUser.objects.create(blocker=self.user1, blocked=self.user2)
        BlockedUser.objects.create(blocker=self.user2, blocked=self.user1)
        
        # Neither should be able to message the other
        self.client.login(username='user1', password='pass123')
        response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
            'message': 'This should fail'
        })
        self.assertEqual(response.status_code, 403)
        
        self.client.login(username='user2', password='pass123')
        response = self.client.post(f'/ajax/send-message/{self.user1.username}/', {
            'message': 'This should also fail'
        })
        self.assertEqual(response.status_code, 403)


class ConversationViewTest(TestCase):
    """Test conversation viewing and navigation"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'pass123')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'pass123')
        
        # Create conversation with messages
        self.conversation = Conversation.objects.create(
            participant1=self.user1,
            participant2=self.user2
        )
        
        Message.objects.create(
            conversation=self.conversation,
            sender=self.user1,
            content='Hello from user1'
        )
        
        Message.objects.create(
            conversation=self.conversation,
            sender=self.user2,
            content='Hello back from user2'
        )

    def test_conversation_view_access(self):
        """Test accessing conversation view"""
        self.client.login(username='user1', password='pass123')
        
        response = self.client.get(f'/conversation/{self.user2.username}/')
        self.assertEqual(response.status_code, 200)
        
        # Should show messages
        self.assertContains(response, 'Hello from user1')
        self.assertContains(response, 'Hello back from user2')

    def test_my_messages_page(self):
        """Test my messages page shows conversations"""
        self.client.login(username='user1', password='pass123')
        
        response = self.client.get(reverse('my_messages'))
        self.assertEqual(response.status_code, 200)
        
        # Should show conversation with user2
        self.assertContains(response, self.user2.username)

    def test_conversation_unauthorized_access(self):
        """Test that users can't access others' conversations"""
        # Create third user
        user3 = User.objects.create_user('user3', 'user3@test.com', 'pass123')
        
        self.client.login(username='user3', password='pass123')
        
        # Try to access conversation between user1 and user2
        response = self.client.get(f'/conversation/{self.user1.username}/')
        
        # Should either create new conversation or show empty state
        self.assertEqual(response.status_code, 200)
        # Should not show messages from user1-user2 conversation
        self.assertNotContains(response, 'Hello from user1')
        self.assertNotContains(response, 'Hello back from user2')