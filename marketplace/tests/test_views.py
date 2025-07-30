from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from decimal import Decimal
import json

from marketplace.models import (
    Game, GameCategory, Category, Profile, Product, Order, 
    Conversation, Message, Transaction
)


class HomeViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.game = Game.objects.create(title="Test Game")
        self.category = Category.objects.create(name="Test Category")

    def test_home_view_status_code(self):
        response = self.client.get(reverse('marketplace:home'))
        self.assertEqual(response.status_code, 200)

    def test_home_view_contains_games(self):
        response = self.client.get(reverse('marketplace:home'))
        self.assertContains(response, "Test Game")


class ProductViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.game = Game.objects.create(title="Test Game")
        self.category = Category.objects.create(name="Test Category")
        
        self.product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title="Test Product",
            description="Test Description",
            price=Decimal('99.99'),
            stock=10
        )

    def test_product_detail_view(self):
        response = self.client.get(
            reverse('marketplace:product_detail', kwargs={'product_id': self.product.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Product")
        self.assertContains(response, "99.99")

    def test_product_creation_requires_login(self):
        response = self.client.get(reverse('marketplace:product_form'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_product_creation_authenticated_user(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('marketplace:product_form'))
        self.assertEqual(response.status_code, 200)

    def test_product_creation_post(self):
        self.client.login(username='testuser', password='testpass123')
        
        data = {
            'game': self.game.id,
            'category': self.category.id,
            'title': 'New Test Product',
            'description': 'New Test Description',
            'price': '149.99',
            'stock': 5,
        }
        
        response = self.client.post(reverse('marketplace:product_form'), data)
        
        # Should redirect after successful creation
        self.assertEqual(response.status_code, 302)
        
        # Verify product was created
        new_product = Product.objects.filter(title='New Test Product').first()
        self.assertIsNotNone(new_product)
        self.assertEqual(new_product.price, Decimal('149.99'))


class OrderViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.buyer = User.objects.create_user(
            username='buyer',
            email='buyer@example.com',
            password='testpass123'
        )
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@example.com',
            password='testpass123'
        )
        
        # Add funds to buyer's profile
        buyer_profile = Profile.objects.get(user=self.buyer)
        buyer_profile.balance = Decimal('200.00')
        buyer_profile.save()
        
        self.game = Game.objects.create(title="Test Game")
        self.category = Category.objects.create(name="Test Category")
        
        self.product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Test Product",
            description="Test Description",
            price=Decimal('99.99'),
            stock=10
        )

    def test_order_creation_requires_login(self):
        response = self.client.post(
            reverse('marketplace:create_order'),
            {'product_id': self.product.id, 'quantity': 1}
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_order_creation_authenticated_user(self):
        self.client.login(username='buyer', password='testpass123')
        
        response = self.client.post(
            reverse('marketplace:create_order'),
            {'product_id': self.product.id, 'quantity': 1}
        )
        
        # Check if order was created
        order = Order.objects.filter(buyer=self.buyer, product=self.product).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.quantity, 1)
        self.assertEqual(order.price, self.product.price)

    def test_my_purchases_view(self):
        self.client.login(username='buyer', password='testpass123')
        
        # Create an order first
        Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )
        
        response = self.client.get(reverse('marketplace:my_purchases'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Product")

    def test_my_sales_view(self):
        self.client.login(username='seller', password='testpass123')
        
        # Create an order first
        Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )
        
        response = self.client.get(reverse('marketplace:my_sales'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Product")


class AuthenticationViewsTest(TestCase):
    def setUp(self):
        self.client = Client()

    def test_registration_view(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)

    def test_user_registration(self):
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'complex_password_123',
            'password2': 'complex_password_123',
        }
        
        response = self.client.post(reverse('register'), data)
        
        # Should redirect after successful registration
        self.assertEqual(response.status_code, 302)
        
        # Verify user was created
        user = User.objects.filter(username='newuser').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, 'newuser@example.com')
        
        # Verify profile was created
        profile = Profile.objects.filter(user=user).first()
        self.assertIsNotNone(profile)

    def test_login_view(self):
        # Create a user first
        User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        
        # Test login
        login_data = {
            'username': 'testuser',
            'password': 'testpass123'
        }
        
        response = self.client.post(reverse('login'), login_data)
        self.assertEqual(response.status_code, 302)  # Redirect after login


class SearchViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.game = Game.objects.create(title="Test Game")
        self.category = Category.objects.create(name="Test Category")
        
        self.user = User.objects.create_user(
            username='seller',
            email='seller@example.com',
            password='testpass123'
        )
        
        self.product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title="Searchable Product",
            description="A product for search testing",
            price=Decimal('99.99'),
            stock=10
        )

    def test_search_view(self):
        response = self.client.get(reverse('marketplace:search_results'))
        self.assertEqual(response.status_code, 200)

    def test_search_with_query(self):
        response = self.client.get(
            reverse('marketplace:search_results'), 
            {'q': 'Searchable'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Searchable Product")

    def test_search_no_results(self):
        response = self.client.get(
            reverse('marketplace:search_results'), 
            {'q': 'NonexistentProduct'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Searchable Product")


class ProfileViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_profile_view_requires_login(self):
        response = self.client.get(reverse('marketplace:settings'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_profile_view_authenticated(self):
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('marketplace:settings'))
        self.assertEqual(response.status_code, 200)

    def test_public_profile_view(self):
        response = self.client.get(
            reverse('marketplace:public_profile', kwargs={'username': 'testuser'})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'testuser')


class APIViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_ajax_request_requires_authentication(self):
        """Test that AJAX requests require authentication"""
        response = self.client.get(
            reverse('marketplace:my_messages'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_ajax_request_authenticated(self):
        """Test authenticated AJAX request"""
        self.client.login(username='testuser', password='testpass123')
        
        response = self.client.get(
            reverse('marketplace:my_messages'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)