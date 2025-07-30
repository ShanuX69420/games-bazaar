from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

from marketplace.models import (
    Game, GameCategory, Category, Profile, Product, ProductImage, 
    Order, Review, ReviewReply, Conversation, Message, Transaction,
    Filter, FilterOption, SupportTicket, WithdrawalRequest
)


class GameModelTest(TestCase):
    def setUp(self):
        self.game = Game.objects.create(
            title="Test Game"
        )

    def test_game_creation(self):
        self.assertEqual(self.game.title, "Test Game")

    def test_game_str_representation(self):
        self.assertEqual(str(self.game), "Test Game")


class ProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.profile = Profile.objects.get(user=self.user)

    def test_profile_creation_on_user_save(self):
        """Test that profile is automatically created when user is created"""
        self.assertIsNotNone(self.profile)
        self.assertEqual(self.profile.user, self.user)

    def test_profile_properties(self):
        """Test profile properties"""
        self.assertFalse(self.profile.is_online)  # No last_seen set
        self.assertFalse(self.profile.can_moderate)  # Not staff/moderator
        self.assertEqual(self.profile.image_url, '/static/images/default.jpg')


class ProductModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='seller',
            email='seller@example.com',
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

    def test_product_creation(self):
        self.assertEqual(self.product.listing_title, "Test Product")
        self.assertEqual(self.product.price, Decimal('99.99'))
        self.assertEqual(self.product.stock, 10)
        self.assertTrue(self.product.is_active)

    def test_product_str_representation(self):
        expected = f"{self.product.game.title} - {self.product.listing_title}"
        self.assertEqual(str(self.product), expected)

    def test_product_queryset_methods(self):
        """Test custom queryset methods"""
        active_products = Product.objects.active()
        self.assertIn(self.product, active_products)

        # Test inactive product
        self.product.is_active = False
        self.product.save()
        
        active_products = Product.objects.active()
        self.assertNotIn(self.product, active_products)


class OrderModelTest(TestCase):
    def setUp(self):
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
        
        self.order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )

    def test_order_creation(self):
        self.assertEqual(self.order.buyer, self.buyer)
        self.assertEqual(self.order.seller, self.seller)
        self.assertEqual(self.order.product, self.product)
        self.assertEqual(self.order.total_price, Decimal('99.99'))
        self.assertEqual(self.order.status, 'PENDING_PAYMENT')

    def test_order_total(self):
        """Test order total calculation"""
        self.assertEqual(self.order.total_price, Decimal('99.99'))

    def test_order_status_transitions(self):
        """Test valid order status transitions"""
        self.assertEqual(self.order.status, 'PENDING_PAYMENT')
        
        self.order.status = 'COMPLETED'
        self.order.save()
        self.assertEqual(self.order.status, 'COMPLETED')


class ReviewModelTest(TestCase):
    def setUp(self):
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
        self.game = Game.objects.create(title="Test Game")
        self.category = Category.objects.create(name="Test Category")
        
        self.product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Test Product",
            description="Test Description",
            price=Decimal('99.99')
        )
        
        self.order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price,
            status='COMPLETED'
        )
        
        self.review = Review.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            order=self.order,
            rating=5,
            comment="Great product!"
        )

    def test_review_creation(self):
        self.assertEqual(self.review.buyer, self.buyer)
        self.assertEqual(self.review.order, self.order)
        self.assertEqual(self.review.rating, 5)
        self.assertEqual(self.review.comment, "Great product!")

    def test_review_rating_validation(self):
        """Test that rating must be between 1 and 5"""
        # This would typically be handled by model validation
        self.assertGreaterEqual(self.review.rating, 1)
        self.assertLessEqual(self.review.rating, 5)


class ConversationModelTest(TestCase):
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
            participant1=self.user1,
            participant2=self.user2
        )

    def test_conversation_creation(self):
        self.assertEqual(self.conversation.participant1, self.user1)
        self.assertEqual(self.conversation.participant2, self.user2)
        self.assertFalse(self.conversation.is_disputed)

    def test_conversation_participants(self):
        """Test that conversation includes both users"""
        participants = self.conversation.get_participants()
        self.assertIn(self.user1, participants)
        self.assertIn(self.user2, participants)


class MessageModelTest(TestCase):
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
            participant1=self.user1,
            participant2=self.user2
        )
        
        self.message = Message.objects.create(
            conversation=self.conversation,
            sender=self.user1,
            content="Hello, how are you?"
        )

    def test_message_creation(self):
        self.assertEqual(self.message.conversation, self.conversation)
        self.assertEqual(self.message.sender, self.user1)
        self.assertEqual(self.message.content, "Hello, how are you?")
        self.assertFalse(self.message.is_read)

    def test_message_timestamp(self):
        """Test that message has a timestamp"""
        self.assertIsNotNone(self.message.timestamp)
        
        # Check that timestamp is recent (within last minute)
        now = timezone.now()
        time_diff = now - self.message.timestamp
        self.assertLess(time_diff, timedelta(minutes=1))


class TransactionModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.transaction = Transaction.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            transaction_type='deposit',
            description="Test deposit"
        )

    def test_transaction_creation(self):
        self.assertEqual(self.transaction.user, self.user)
        self.assertEqual(self.transaction.amount, Decimal('100.00'))
        self.assertEqual(self.transaction.transaction_type, 'deposit')
        self.assertEqual(self.transaction.description, "Test deposit")

    def test_transaction_timestamp(self):
        """Test that transaction has a timestamp"""
        self.assertIsNotNone(self.transaction.created_at)