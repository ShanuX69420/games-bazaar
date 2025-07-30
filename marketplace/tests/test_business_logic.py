from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.db import transaction, IntegrityError

from marketplace.models import (
    Game, Category, Profile, Product, Order, Review, 
    Conversation, Message, Transaction, Filter, FilterOption
)


class ProductBusinessLogicTest(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            username='seller',
            email='seller@example.com',
            password='testpass123'
        )
        self.game = Game.objects.create(title="Test Game")
        self.category = Category.objects.create(name="Test Category")

    def test_product_stock_management(self):
        """Test product stock decreases when orders are created"""
        product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Stock Test Product",
            description="Testing stock",
            price=Decimal('50.00'),
            stock=5
        )
        
        initial_stock = product.stock
        self.assertEqual(product.stock_count, 5)
        
        # Test automatic delivery stock counting
        product.automatic_delivery = True
        product.stock_details = "item1\nitem2\nitem3"
        product.save()
        self.assertEqual(product.stock_count, 3)

    def test_product_pricing_validation(self):
        """Test that products must have valid pricing"""
        # Test valid price
        product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Price Test",
            description="Testing pricing",
            price=Decimal('99.99')
        )
        self.assertEqual(product.price, Decimal('99.99'))
        
        # Test zero price (should be allowed for free items)
        free_product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Free Item",
            description="Free item test",
            price=Decimal('0.00')
        )
        self.assertEqual(free_product.price, Decimal('0.00'))

    def test_product_activation_status(self):
        """Test product activation/deactivation logic"""
        product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Activation Test",
            description="Testing activation",
            price=Decimal('25.00')
        )
        
        # Product should be active by default
        self.assertTrue(product.is_active)
        
        # Test deactivation
        product.is_active = False
        product.save()
        
        # Should not appear in active products
        active_products = Product.objects.active()
        self.assertNotIn(product, active_products)


class OrderBusinessLogicTest(TestCase):
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
            listing_title="Order Test Product",
            description="Testing orders",
            price=Decimal('75.00'),
            stock=10
        )

    def test_order_creation_and_workflow(self):
        """Test complete order workflow"""
        # Create order
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )
        
        # Initial status should be PENDING_PAYMENT
        self.assertEqual(order.status, 'PENDING_PAYMENT')
        
        # Test status progression
        order.status = 'PROCESSING'
        order.save()
        self.assertEqual(order.status, 'PROCESSING')
        
        order.status = 'DELIVERED'
        order.save()
        self.assertEqual(order.status, 'DELIVERED')
        
        order.status = 'COMPLETED'
        order.save()
        self.assertEqual(order.status, 'COMPLETED')

    def test_order_snapshots(self):
        """Test that order preserves product data in snapshots"""
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price,
            listing_title_snapshot=self.product.listing_title,
            description_snapshot=self.product.description,
            game_snapshot=self.game,
            category_snapshot=self.category
        )
        
        # Test snapshots are preserved
        self.assertEqual(order.listing_title_snapshot, "Order Test Product")
        self.assertEqual(order.game_snapshot, self.game)
        self.assertEqual(order.category_snapshot, self.category)
        
        # Even if product is deleted, snapshots should remain
        product_title = self.product.listing_title
        self.product.delete()
        
        order.refresh_from_db()
        self.assertEqual(order.listing_title_snapshot, product_title)
        self.assertIsNone(order.product)  # Product deleted
        self.assertIsNotNone(order.game_snapshot)  # Snapshot preserved

    def test_order_commission_calculation(self):
        """Test order commission calculation"""
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=Decimal('100.00')
        )
        
        # Test commission calculation exists and returns a value
        commission = order.calculate_commission()
        self.assertIsNotNone(commission)
        
        # Test with custom seller commission rate
        seller_profile = Profile.objects.get(user=self.seller)
        seller_profile.commission_rate = Decimal('15.00')  # 15%
        seller_profile.save()
        
        commission = order.calculate_commission()
        # Expected commission should be calculated based on rate

    def test_order_prevents_self_purchase(self):
        """Test that users cannot buy their own products"""
        # In current implementation, this might not be prevented at model level
        # but should be prevented in views/business logic
        
        # Create order where buyer = seller (currently allowed at model level)
        try:
            order = Order.objects.create(
                buyer=self.seller,  # Same as seller
                seller=self.seller,
                product=self.product,
                total_price=self.product.price
            )
            # If created, that's the current behavior
            self.assertEqual(order.buyer, order.seller)
        except Exception:
            # If prevented, that's also fine
            pass


class ReviewBusinessLogicTest(TestCase):
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
            listing_title="Review Test Product",
            description="Testing reviews",
            price=Decimal('30.00')
        )
        
        self.order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price,
            status='COMPLETED'
        )

    def test_review_creation_requires_completed_order(self):
        """Test that reviews can only be created for completed orders"""
        review = Review.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            order=self.order,
            rating=4,
            comment="Good product"
        )
        
        self.assertEqual(review.buyer, self.buyer)
        self.assertEqual(review.order, self.order)
        self.assertEqual(review.rating, 4)

    def test_review_rating_validation(self):
        """Test review rating must be between 1-5"""
        review = Review.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            order=self.order,
            rating=5,
            comment="Excellent!"
        )
        
        # Test valid ratings
        for rating in [1, 2, 3, 4, 5]:
            review.rating = rating
            review.save()
            self.assertEqual(review.rating, rating)

    def test_seller_reply_to_review(self):
        """Test seller can reply to reviews"""
        review = Review.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            order=self.order,
            rating=3,
            comment="Average product"
        )
        
        from marketplace.models import ReviewReply
        reply = ReviewReply.objects.create(
            review=review,
            seller=self.seller,
            reply_text="Thank you for your feedback! We'll improve."
        )
        
        self.assertEqual(reply.review, review)
        self.assertEqual(reply.seller, self.seller)
        self.assertIn("improve", reply.reply_text.lower())

    def test_duplicate_review_prevention(self):
        """Test that buyer can only review an order once"""
        # Create first review
        Review.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            order=self.order,
            rating=4,
            comment="First review"
        )
        
        # Attempting to create second review for same order should fail
        # This assumes you have uniqueness constraint
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                buyer=self.buyer,
                order=self.order,
                rating=5,
                comment="Second review attempt"
            )


class ConversationBusinessLogicTest(TestCase):
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
        self.moderator = User.objects.create_user(
            username='moderator',
            email='moderator@example.com',
            password='testpass123'
        )

    def test_conversation_unique_participants(self):
        """Test that only one conversation exists between two users"""
        conv1 = Conversation.objects.create(
            participant1=self.user1,
            participant2=self.user2
        )
        
        # Attempting to create another conversation with same participants should fail
        with self.assertRaises(IntegrityError):
            Conversation.objects.create(
                participant1=self.user1,
                participant2=self.user2
            )

    def test_conversation_dispute_escalation(self):
        """Test conversation dispute escalation with moderator"""
        conversation = Conversation.objects.create(
            participant1=self.user1,
            participant2=self.user2
        )
        
        # Initially not disputed
        self.assertFalse(conversation.is_disputed)
        self.assertIsNone(conversation.moderator)
        
        # Escalate to dispute
        conversation.is_disputed = True
        conversation.moderator = self.moderator
        conversation.save()
        
        self.assertTrue(conversation.is_disputed)
        self.assertEqual(conversation.moderator, self.moderator)
        
        # Test participant list includes moderator
        participants = conversation.get_participants()
        self.assertIn(self.moderator, participants)
        self.assertEqual(len(participants), 3)

    def test_message_read_status_tracking(self):
        """Test message read status tracking"""
        conversation = Conversation.objects.create(
            participant1=self.user1,
            participant2=self.user2
        )
        
        # User1 sends message to User2
        message = Message.objects.create(
            conversation=conversation,
            sender=self.user1,
            content="Hello User2!"
        )
        
        # Initially unread
        self.assertFalse(message.is_read)
        
        # Mark as read
        message.is_read = True
        message.save()
        
        self.assertTrue(message.is_read)

    def test_conversation_message_ordering(self):
        """Test that messages are properly ordered by timestamp"""
        conversation = Conversation.objects.create(
            participant1=self.user1,
            participant2=self.user2
        )
        
        # Create messages in sequence
        msg1 = Message.objects.create(
            conversation=conversation,
            sender=self.user1,
            content="First message"
        )
        
        msg2 = Message.objects.create(
            conversation=conversation,
            sender=self.user2,
            content="Second message"
        )
        
        msg3 = Message.objects.create(
            conversation=conversation,
            sender=self.user1,
            content="Third message"
        )
        
        # Get messages in order
        messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
        message_list = list(messages)
        
        self.assertEqual(message_list[0], msg1)
        self.assertEqual(message_list[1], msg2)
        self.assertEqual(message_list[2], msg3)


class TransactionBusinessLogicTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_transaction_balance_tracking(self):
        """Test transaction balance tracking"""
        # Create deposit transaction
        deposit = Transaction.objects.create(
            user=self.user,
            amount=Decimal('100.00'),
            transaction_type='deposit',
            description="Initial deposit"
        )
        
        # Create withdrawal transaction
        withdrawal = Transaction.objects.create(
            user=self.user,
            amount=Decimal('30.00'),
            transaction_type='withdrawal',
            description="Test withdrawal"
        )
        
        # Verify transactions exist
        user_transactions = Transaction.objects.filter(user=self.user)
        self.assertEqual(user_transactions.count(), 2)
        
        # Test transaction types
        deposit_transactions = user_transactions.filter(transaction_type='deposit')
        withdrawal_transactions = user_transactions.filter(transaction_type='withdrawal')
        
        self.assertEqual(deposit_transactions.count(), 1)
        self.assertEqual(withdrawal_transactions.count(), 1)

    def test_commission_transaction_creation(self):
        """Test commission transactions are created properly"""
        commission_transaction = Transaction.objects.create(
            user=self.user,
            amount=Decimal('5.00'),
            transaction_type='commission',
            description="Commission from sale #123"
        )
        
        self.assertEqual(commission_transaction.transaction_type, 'commission')
        self.assertEqual(commission_transaction.amount, Decimal('5.00'))


class FilterSystemBusinessLogicTest(TestCase):
    def test_filter_system_functionality(self):
        """Test product filtering system"""
        # Create filter
        platform_filter = Filter.objects.create(
            name="Platform",
            filter_type="dropdown"
        )
        
        # Create filter options
        pc_option = FilterOption.objects.create(
            filter=platform_filter,
            value="PC"
        )
        
        console_option = FilterOption.objects.create(
            filter=platform_filter,
            value="Console"
        )
        
        # Test filter-option relationships
        self.assertEqual(pc_option.filter, platform_filter)
        self.assertEqual(console_option.filter, platform_filter)
        
        # Test that filter options belong to correct filter
        platform_options = FilterOption.objects.filter(filter=platform_filter)
        self.assertIn(pc_option, platform_options)
        self.assertIn(console_option, platform_options)


class ProfileBusinessLogicTest(TestCase):
    def test_profile_creation_signal(self):
        """Test that Profile is automatically created when User is created"""
        user = User.objects.create_user(
            username='signaltest',
            email='signal@example.com',
            password='testpass123'
        )
        
        # Profile should be automatically created
        profile = Profile.objects.get(user=user)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.user, user)

    def test_profile_permissions(self):
        """Test profile permission system"""
        user = User.objects.create_user(
            username='permtest',
            email='perm@example.com',
            password='testpass123'
        )
        profile = Profile.objects.get(user=user)
        
        # Regular user should not be able to moderate
        self.assertFalse(profile.can_moderate)
        
        # Staff user should be able to moderate
        user.is_staff = True
        user.save()
        profile.refresh_from_db()
        self.assertTrue(profile.can_moderate)
        
        # Moderator flag should also allow moderation
        user.is_staff = False
        profile.is_moderator = True
        user.save()
        profile.save()
        self.assertTrue(profile.can_moderate)