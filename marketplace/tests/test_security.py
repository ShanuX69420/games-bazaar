"""
Security Tests - Based on comprehensive manual security testing
Tests XSS prevention, file upload security, UUID enumeration prevention
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
import tempfile
import os

from marketplace.models import Order, Message, Conversation, Product, Game, Category
from marketplace.views import sanitize_user_input, validate_uploaded_file


class XSSSecurityTest(TestCase):
    """Test XSS vulnerability prevention - matches manual Test 1"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user('testuser1', 'test1@example.com', 'testpass123')
        self.user2 = User.objects.create_user('testuser2', 'test2@example.com', 'testpass123')
        self.client.login(username='testuser1', password='testpass123')

    def test_xss_prevention_in_chat_messages(self):
        """Test that XSS scripts in chat messages are escaped, not executed"""
        xss_payloads = [
            '<script>alert("XSS")</script>',
            '<img src=x onerror=alert("XSS")>',
            'javascript:alert("XSS")',
            '<svg onload=alert("XSS")>',
        ]
        
        for payload in xss_payloads:
            # Test backend sanitization
            sanitized = sanitize_user_input(payload)
            self.assertNotIn('<script', sanitized)
            self.assertNotIn('javascript:', sanitized)
            self.assertNotIn('onerror=', sanitized)
            
            # Ensure content is escaped, not removed completely
            self.assertIn('&lt;', sanitized)  # < should be escaped
            
            # Test via chat message sending
            response = self.client.post(f'/ajax/send-message/{self.user2.username}/', {
                'message': payload
            })
            
            # Should succeed but content should be sanitized
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data['status'], 'success')

    def test_safe_html_template_filter(self):
        """Test that template filter properly escapes HTML"""
        from marketplace.templatetags.safe_html import safe_user_html
        
        dangerous_content = '<script>alert("XSS")</script><p>Normal text</p>'
        safe_content = safe_user_html(dangerous_content)
        
        # Should escape dangerous tags
        self.assertNotIn('<script>', str(safe_content))
        self.assertIn('&lt;script&gt;', str(safe_content))


class FileUploadSecurityTest(TestCase):
    """Test file upload security - matches manual Test 2"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass123')
        self.client.login(username='testuser', password='testpass123')

    def test_dangerous_filename_rejection(self):
        """Test that dangerous filenames are rejected"""
        dangerous_filenames = [
            '../../../etc/passwd.jpg',
            'test\\file.jpg',
            'file<script>.jpg',
            'file|pipe.jpg',
            'file?.jpg',
            'file*.jpg',
        ]
        
        for filename in dangerous_filenames:
            with self.assertRaises(ValidationError) as context:
                # Create a fake image file with dangerous name
                fake_file = SimpleUploadedFile(
                    filename, 
                    b'fake image content',
                    content_type='image/jpeg'
                )
                validate_uploaded_file(fake_file, max_size_mb=5)
            
            self.assertIn('dangerous characters', str(context.exception))

    def test_file_extension_validation(self):
        """Test that only allowed file extensions are accepted"""
        invalid_extensions = ['file.txt', 'script.php', 'malware.exe', 'data.json']
        
        for filename in invalid_extensions:
            with self.assertRaises(ValidationError):
                fake_file = SimpleUploadedFile(
                    filename,
                    b'fake content',
                    content_type='text/plain'
                )
                validate_uploaded_file(fake_file, max_size_mb=5)

    def test_file_size_limits(self):
        """Test file size restrictions"""
        # Test oversized file (6MB when limit is 5MB)
        oversized_content = b'x' * (6 * 1024 * 1024)  # 6MB
        
        with self.assertRaises(ValidationError) as context:
            oversized_file = SimpleUploadedFile(
                'large_image.jpg',
                oversized_content,
                content_type='image/jpeg'
            )
            validate_uploaded_file(oversized_file, max_size_mb=5)
        
        self.assertIn('exceed 5MB', str(context.exception))

    def test_minimum_file_size(self):
        """Test rejection of too-small files (likely empty/corrupted)"""
        with self.assertRaises(ValidationError) as context:
            tiny_file = SimpleUploadedFile(
                'tiny.jpg',
                b'x',  # Only 1 byte
                content_type='image/jpeg'
            )
            validate_uploaded_file(tiny_file, max_size_mb=5)
        
        self.assertIn('too small', str(context.exception))

    def test_fake_image_file_detection(self):
        """Test detection of text files renamed as images"""
        # This would require implementing magic byte checking
        # For now, test that MIME type validation works
        fake_image = SimpleUploadedFile(
            'fake_image.jpg',
            b'This is actually a text file, not an image!',
            content_type='text/plain'  # Wrong content type
        )
        
        # The validation should catch this mismatch
        with self.assertRaises(ValidationError):
            validate_uploaded_file(fake_image, max_size_mb=5)


class UUIDSecurityTest(TestCase):
    """Test UUID-based order enumeration prevention - matches manual Test 4"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('testuser', 'test@example.com', 'testpass123')
        self.game = Game.objects.create(title='Test Game')
        self.category = Category.objects.create(name='Test Category')
        
        # Create a test product and order
        self.product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title='Test Product',
            description='Test description',
            price=10.00,
            stock_quantity=5
        )
        
        self.order = Order.objects.create(
            buyer=self.user,
            seller=self.user,
            product=self.product,
            quantity=1,
            total_amount=10.00
        )
        
        self.client.login(username='testuser', password='testpass123')

    def test_uuid_order_id_format(self):
        """Test that order IDs use UUID format, not sequential numbers"""
        # Order ID should be in format #XXXX-XXXX-XXXX
        self.assertIsNotNone(self.order.order_id)
        self.assertTrue(self.order.order_id.startswith('#'))
        
        # Should contain hyphens in UUID format
        clean_id = self.order.order_id[1:]  # Remove #
        parts = clean_id.split('-')
        self.assertEqual(len(parts), 3)
        self.assertEqual(len(parts[0]), 4)
        self.assertEqual(len(parts[1]), 4)
        self.assertEqual(len(parts[2]), 4)

    def test_order_url_uses_clean_uuid(self):
        """Test that order URLs use clean UUIDs without # character"""
        clean_id = self.order.clean_order_id
        self.assertFalse(clean_id.startswith('#'))
        
        # URL should not contain %23 (URL-encoded #)
        order_url = reverse('order_detail', args=[clean_id])
        self.assertNotIn('%23', order_url)
        self.assertIn(clean_id, order_url)

    def test_order_enumeration_prevention(self):
        """Test that guessing order URLs returns 404"""
        fake_uuids = [
            '1234-5678-9ABC',
            'AAAA-BBBB-CCCC',
            'TEST-TEST-TEST',
            'FAKE-UUID-HERE'
        ]
        
        for fake_uuid in fake_uuids:
            response = self.client.get(reverse('order_detail', args=[fake_uuid]))
            self.assertEqual(response.status_code, 404)

    def test_sequential_order_urls_blocked(self):
        """Test that old sequential URLs no longer work"""
        # Try accessing with sequential numbers (old vulnerable pattern)
        sequential_ids = [1, 2, 3, 542, 1000]
        
        for seq_id in sequential_ids:
            # This should fail because URL pattern expects string, not int
            with self.assertRaises(Exception):
                reverse('order_detail', args=[seq_id])

    def test_legitimate_order_access(self):
        """Test that legitimate order access still works"""
        response = self.client.get(reverse('order_detail', args=[self.order.clean_order_id]))
        self.assertEqual(response.status_code, 200)


class AuthorizationTest(TestCase):
    """Test access control and authorization"""
    
    def setUp(self):
        self.client = Client()
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'pass123')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'pass123')
        
        self.game = Game.objects.create(title='Test Game')
        self.category = Category.objects.create(name='Test Category')
        self.product = Product.objects.create(
            seller=self.user1,
            game=self.game,
            category=self.category,
            listing_title='Test Product',
            description='Test description',
            price=10.00,
            stock_quantity=5
        )
        
        self.order = Order.objects.create(
            buyer=self.user1,
            seller=self.user2,
            product=self.product,
            quantity=1,
            total_amount=10.00
        )

    def test_order_access_authorization(self):
        """Test that users can only access their own orders"""
        # user1 should be able to access their order
        self.client.login(username='user1', password='pass123')
        response = self.client.get(reverse('order_detail', args=[self.order.clean_order_id]))
        self.assertEqual(response.status_code, 200)
        
        # user2 (seller) should also be able to access
        self.client.login(username='user2', password='pass123')
        response = self.client.get(reverse('order_detail', args=[self.order.clean_order_id]))
        self.assertEqual(response.status_code, 200)
        
        # Create a third user who shouldn't have access
        user3 = User.objects.create_user('user3', 'user3@test.com', 'pass123')
        self.client.login(username='user3', password='pass123')
        response = self.client.get(reverse('order_detail', args=[self.order.clean_order_id]))
        self.assertEqual(response.status_code, 403)  # Forbidden

    def test_unauthenticated_access_blocked(self):
        """Test that unauthenticated users cannot access orders"""
        self.client.logout()
        response = self.client.get(reverse('order_detail', args=[self.order.clean_order_id]))
        self.assertEqual(response.status_code, 302)  # Redirect to login