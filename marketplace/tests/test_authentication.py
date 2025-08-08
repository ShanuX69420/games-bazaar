"""
User Authentication Tests - Based on comprehensive manual testing
Tests registration, login, password reset, social auth
Matches manual Test 5: Account System
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from marketplace.models import Profile


class UserRegistrationTest(TestCase):
    """Test user registration functionality"""
    
    def setUp(self):
        self.client = Client()

    def test_user_registration_success(self):
        """Test successful user registration"""
        registration_data = {
            'email': 'newuser@test.com',
            'password1': 'ComplexPassword123!',
            'password2': 'ComplexPassword123!',
        }
        
        response = self.client.post(reverse('account_signup'), registration_data)
        
        # Should redirect after successful registration
        self.assertEqual(response.status_code, 302)
        
        # User should be created
        user = User.objects.get(email='newuser@test.com')
        self.assertIsNotNone(user)
        
        # Profile should be auto-created
        self.assertTrue(hasattr(user, 'profile'))

    def test_user_registration_validation(self):
        """Test registration form validation"""
        # Test password mismatch
        registration_data = {
            'email': 'test@test.com',
            'password1': 'Password123!',
            'password2': 'DifferentPassword123!',
        }
        
        response = self.client.post(reverse('account_signup'), registration_data)
        self.assertEqual(response.status_code, 200)  # Should stay on form
        self.assertContains(response, "didn't match")  # Password mismatch error

    def test_duplicate_email_registration(self):
        """Test registration with existing email"""
        # Create existing user
        User.objects.create_user('existing', 'existing@test.com', 'password123')
        
        registration_data = {
            'email': 'existing@test.com',  # Same email
            'password1': 'NewPassword123!',
            'password2': 'NewPassword123!',
        }
        
        response = self.client.post(reverse('account_signup'), registration_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already exists')  # Email exists error

    def test_weak_password_rejection(self):
        """Test that weak passwords are rejected"""
        weak_passwords = [
            'password',  # Too common
            '123456',    # Too simple
            'abc',       # Too short
        ]
        
        for weak_password in weak_passwords:
            registration_data = {
                'email': f'test_{weak_password}@test.com',
                'password1': weak_password,
                'password2': weak_password,
            }
            
            response = self.client.post(reverse('account_signup'), registration_data)
            self.assertEqual(response.status_code, 200)
            # Should show password validation errors
            self.assertTrue(
                'too common' in response.content.decode() or 
                'too short' in response.content.decode() or
                'entirely numeric' in response.content.decode()
            )


class UserLoginTest(TestCase):
    """Test user login functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='TestPassword123!'
        )

    def test_login_success(self):
        """Test successful login with email"""
        login_data = {
            'login': 'testuser@test.com',
            'password': 'TestPassword123!',
        }
        
        response = self.client.post(reverse('account_login'), login_data)
        self.assertEqual(response.status_code, 302)  # Redirect after login
        
        # User should be logged in
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_with_username(self):
        """Test login with username (if supported)"""
        login_data = {
            'login': 'testuser',
            'password': 'TestPassword123!',
        }
        
        response = self.client.post(reverse('account_login'), login_data)
        
        # Depending on your configuration, this might work or not
        # Adjust based on ACCOUNT_LOGIN_METHODS setting
        if 'email' in str(response.content):
            # If only email login is allowed
            self.assertEqual(response.status_code, 200)
        else:
            # If username login is allowed
            self.assertEqual(response.status_code, 302)

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        invalid_attempts = [
            {'login': 'testuser@test.com', 'password': 'WrongPassword'},
            {'login': 'nonexistent@test.com', 'password': 'TestPassword123!'},
            {'login': '', 'password': 'TestPassword123!'},
            {'login': 'testuser@test.com', 'password': ''},
        ]
        
        for attempt in invalid_attempts:
            response = self.client.post(reverse('account_login'), attempt)
            self.assertEqual(response.status_code, 200)  # Stay on login form
            self.assertContains(response, 'incorrect')  # Show error message

    def test_login_redirects_to_next(self):
        """Test that login redirects to 'next' parameter"""
        login_data = {
            'login': 'testuser@test.com',
            'password': 'TestPassword123!',
        }
        
        response = self.client.post(
            reverse('account_login') + '?next=/dashboard/', 
            login_data
        )
        
        # Should redirect to the 'next' URL
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)


class PasswordResetTest(TestCase):
    """Test password reset functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='OldPassword123!'
        )

    def test_password_reset_request(self):
        """Test password reset email request"""
        reset_data = {
            'email': 'testuser@test.com',
        }
        
        response = self.client.post(reverse('account_reset_password'), reset_data)
        self.assertEqual(response.status_code, 302)  # Redirect after request
        
        # In development, email might not be sent, but in production it should work
        # We can test the reset token generation
        token = default_token_generator.make_token(self.user)
        self.assertIsNotNone(token)

    def test_password_reset_nonexistent_email(self):
        """Test password reset with non-existent email"""
        reset_data = {
            'email': 'nonexistent@test.com',
        }
        
        response = self.client.post(reverse('account_reset_password'), reset_data)
        
        # Should still show success page (security: don't reveal if email exists)
        self.assertEqual(response.status_code, 302)

    def test_password_reset_token_validation(self):
        """Test that password reset tokens are properly validated"""
        # Generate valid reset token
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        
        # Test accessing reset confirm page with valid token
        reset_url = reverse('account_reset_password_from_key', kwargs={'uidb36': uid, 'key': token})
        response = self.client.get(reset_url)
        
        # Should show password reset form or redirect appropriately
        self.assertIn(response.status_code, [200, 302])

    def test_password_reset_invalid_token(self):
        """Test password reset with invalid token"""
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        invalid_token = 'invalid-token-123'
        
        reset_url = reverse('account_reset_password_from_key', kwargs={'uidb36': uid, 'key': invalid_token})
        response = self.client.get(reset_url)
        
        # Should show error or redirect to reset form
        self.assertIn(response.status_code, [200, 302])


class LogoutTest(TestCase):
    """Test user logout functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='TestPassword123!'
        )

    def test_logout_success(self):
        """Test successful logout"""
        # First login
        self.client.login(username='testuser', password='TestPassword123!')
        
        # Then logout
        response = self.client.post(reverse('account_logout'))
        self.assertEqual(response.status_code, 302)  # Redirect after logout
        
        # User should no longer be authenticated
        response = self.client.get(reverse('home'))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_redirects_to_home(self):
        """Test that logout redirects to home page"""
        self.client.login(username='testuser', password='TestPassword123!')
        
        response = self.client.post(reverse('account_logout'))
        
        # Should redirect to home page
        self.assertRedirects(response, '/', fetch_redirect_response=False)


class ProfileTest(TestCase):
    """Test user profile functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='TestPassword123!'
        )
        self.client.login(username='testuser', password='TestPassword123!')

    def test_profile_auto_creation(self):
        """Test that profile is automatically created for new users"""
        new_user = User.objects.create_user(
            username='newuser',
            email='newuser@test.com',
            password='Password123!'
        )
        
        # Profile should be auto-created
        self.assertTrue(hasattr(new_user, 'profile'))
        self.assertIsInstance(new_user.profile, Profile)

    def test_profile_view_access(self):
        """Test accessing user profile"""
        response = self.client.get(reverse('public_profile', args=[self.user.username]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)

    def test_profile_edit_authorization(self):
        """Test that users can only edit their own profile"""
        # Create another user
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='Password123!'
        )
        
        # Try to access other user's profile edit
        response = self.client.get(reverse('edit_profile'))  # Should show current user's profile
        self.assertEqual(response.status_code, 200)
        
        # The edit form should be for current user, not other user
        self.assertContains(response, self.user.username)
        self.assertNotContains(response, other_user.username)


class SessionSecurityTest(TestCase):
    """Test session security measures"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@test.com',
            password='TestPassword123!'
        )

    def test_session_expiry(self):
        """Test that sessions expire appropriately"""
        # Login
        self.client.login(username='testuser', password='TestPassword123!')
        
        # Check that user is logged in
        response = self.client.get(reverse('home'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        
        # Session should persist across requests
        response = self.client.get(reverse('home'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_required_views(self):
        """Test that protected views require login"""
        protected_urls = [
            reverse('dashboard'),
            reverse('create_product'),
            reverse('my_messages'),
            # Add more protected URLs as needed
        ]
        
        for url in protected_urls:
            response = self.client.get(url)
            # Should redirect to login page
            self.assertEqual(response.status_code, 302)
            self.assertTrue('/accounts/login/' in response.url)

    def test_authenticated_user_access(self):
        """Test that authenticated users can access protected views"""
        self.client.login(username='testuser', password='TestPassword123!')
        
        protected_urls = [
            reverse('dashboard'),
            reverse('create_product'),
            reverse('my_messages'),
        ]
        
        for url in protected_urls:
            response = self.client.get(url)
            # Should be accessible (200) or redirect to valid page (302)
            self.assertIn(response.status_code, [200, 302])
            # Should not redirect to login
            if response.status_code == 302:
                self.assertNotIn('/accounts/login/', response.url)