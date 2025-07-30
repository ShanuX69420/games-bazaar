from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal

from marketplace.models import Game, Category, Profile, Transaction


class BasicModelTest(TestCase):
    """Basic model tests that should work"""
    
    def test_game_creation(self):
        """Test Game model creation"""
        game = Game.objects.create(title="Test Game")
        self.assertEqual(game.title, "Test Game")
        self.assertEqual(str(game), "Test Game")

    def test_category_creation(self):
        """Test Category model creation"""
        category = Category.objects.create(name="Test Category")
        self.assertEqual(category.name, "Test Category")

    def test_profile_creation(self):
        """Test Profile is created when User is created"""
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Profile should be automatically created
        profile = Profile.objects.get(user=user)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.user, user)
        self.assertEqual(str(profile), 'testuser Profile')

    def test_profile_properties(self):
        """Test Profile properties"""
        user = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )
        profile = Profile.objects.get(user=user)
        
        # Test default values
        self.assertFalse(profile.is_online)
        self.assertFalse(profile.can_moderate)
        self.assertTrue(profile.show_listings_on_site)
        self.assertEqual(profile.image_url, '/static/images/default.jpg')

    def test_transaction_creation(self):
        """Test Transaction model creation"""
        user = User.objects.create_user(
            username='testuser3',
            email='test3@example.com',
            password='testpass123'
        )
        
        transaction = Transaction.objects.create(
            user=user,
            amount=Decimal('100.00'),
            transaction_type='deposit',
            description="Test deposit"
        )
        
        self.assertEqual(transaction.user, user)
        self.assertEqual(transaction.amount, Decimal('100.00'))
        self.assertEqual(transaction.transaction_type, 'deposit')
        self.assertEqual(transaction.description, "Test deposit")
        self.assertIsNotNone(transaction.created_at)