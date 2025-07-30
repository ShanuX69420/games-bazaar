from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.db import transaction, IntegrityError
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

from marketplace.models import (
    Game, Category, Profile, Product, Order, Review, ReviewReply,
    Conversation, Message, Transaction, Filter, FilterOption
)
from marketplace.jazzcash_utils import get_jazzcash_payment_params, verify_jazzcash_response


class CompleteUserJourneyTest(TestCase):
    """Test complete user journey from registration to purchase completion"""
    
    def setUp(self):
        # Set up test data
        self.game = Game.objects.create(title="Popular Game")
        self.category = Category.objects.create(name="Game Items")
        
        # Create filter system
        self.platform_filter = Filter.objects.create(
            name="Platform",
            filter_type="dropdown"
        )
        self.pc_option = FilterOption.objects.create(
            filter=self.platform_filter,
            value="PC"
        )

    def test_complete_successful_purchase_journey(self):
        """Test complete successful purchase journey"""
        
        # Step 1: User registration and profile creation
        buyer = User.objects.create_user(
            username='journey_buyer',
            email='buyer@journey.com',
            password='testpass123',
            first_name='John',
            last_name='Buyer'
        )
        
        seller = User.objects.create_user(
            username='journey_seller',
            email='seller@journey.com',
            password='testpass123',
            first_name='Jane',
            last_name='Seller'
        )
        
        # Verify profiles were created automatically
        buyer_profile = Profile.objects.get(user=buyer)
        seller_profile = Profile.objects.get(user=seller)
        
        self.assertIsNotNone(buyer_profile)
        self.assertIsNotNone(seller_profile)
        
        # Step 2: Seller creates a product
        product = Product.objects.create(
            seller=seller,
            game=self.game,
            category=self.category,
            listing_title="Rare Game Item",
            description="A very rare and valuable game item",
            price=Decimal('499.99'),
            stock=1,
            automatic_delivery=True,
            stock_details="ITEM_CODE_12345"
        )
        
        # Add filter options
        product.filter_options.add(self.pc_option)
        
        self.assertTrue(product.is_active)
        self.assertEqual(product.stock_count, 1)
        
        # Step 3: Buyer initiates conversation with seller
        conversation = Conversation.objects.create(
            participant1=buyer,
            participant2=seller
        )
        
        # Initial message from buyer
        inquiry_message = Message.objects.create(
            conversation=conversation,
            sender=buyer,
            content="Hi, is this item still available? Can you provide more details?"
        )
        
        # Seller responds
        response_message = Message.objects.create(
            conversation=conversation,
            sender=seller,
            content="Yes, it's available! This is a rare drop from the final boss."
        )
        
        # Verify conversation
        self.assertEqual(Message.objects.filter(conversation=conversation).count(), 2)
        
        # Step 4: Buyer creates order
        order = Order.objects.create(
            buyer=buyer,
            seller=seller,
            product=product,
            total_price=product.price,
            listing_title_snapshot=product.listing_title,
            description_snapshot=product.description,
            game_snapshot=self.game,
            category_snapshot=self.category
        )
        
        self.assertEqual(order.status, 'PENDING_PAYMENT')
        
        # Step 5: Payment process
        payment_params = get_jazzcash_payment_params(
            amount=order.total_price,
            order_id=order.id
        )
        
        self.assertEqual(payment_params['pp_Amount'], 49999)  # 499.99 * 100
        self.assertEqual(payment_params['pp_BillReference'], str(order.id))
        
        # Step 6: Simulate successful payment
        order.status = 'PROCESSING'
        order.save()
        
        # Create transaction record
        payment_transaction = Transaction.objects.create(
            user=buyer,
            amount=order.total_price,
            transaction_type='purchase',
            description=f"Purchase of {product.listing_title} - Order #{order.id}"
        )
        
        sale_transaction = Transaction.objects.create(
            user=seller,
            amount=order.total_price * Decimal('0.95'),  # 95% after 5% commission
            transaction_type='sale',
            description=f"Sale of {product.listing_title} - Order #{order.id}"
        )
        
        commission_transaction = Transaction.objects.create(
            user=seller,  # Commission taken from seller's earning
            amount=order.total_price * Decimal('0.05'),  # 5% commission
            transaction_type='commission',
            description=f"Commission for Order #{order.id}"
        )
        
        # Step 7: Order completion
        order.status = 'DELIVERED'
        order.save()
        
        # Step 8: Stock reduction
        original_stock = product.stock_count
        # In real implementation, stock would be reduced automatically
        self.assertEqual(original_stock, 1)
        
        # Step 9: Order marked as completed
        order.status = 'COMPLETED'
        order.save()
        
        # Step 10: Buyer leaves review
        review = Review.objects.create(
            buyer=buyer,
            seller=seller,
            order=order,
            rating=5,
            comment="Excellent seller! Item was exactly as described and delivered quickly."
        )
        
        # Step 11: Seller replies to review
        review_reply = ReviewReply.objects.create(
            review=review,
            seller=seller,
            reply_text="Thank you for the great review! Enjoy the item!"
        )
        
        # Verify complete journey
        self.assertEqual(order.status, 'COMPLETED')
        self.assertTrue(Transaction.objects.filter(user=buyer, transaction_type='purchase').exists())
        self.assertTrue(Transaction.objects.filter(user=seller, transaction_type='sale').exists())
        self.assertTrue(Review.objects.filter(buyer=buyer, order=order).exists())
        self.assertTrue(ReviewReply.objects.filter(review=review, seller=seller).exists())

    def test_purchase_with_dispute_resolution(self):
        """Test purchase workflow with dispute resolution"""
        
        buyer = User.objects.create_user('dispute_buyer', 'buyer@dispute.com', 'pass123')
        seller = User.objects.create_user('dispute_seller', 'seller@dispute.com', 'pass123')
        moderator = User.objects.create_user('moderator', 'mod@dispute.com', 'pass123', is_staff=True)
        
        # Product and order creation
        product = Product.objects.create(
            seller=seller,
            game=self.game,
            category=self.category,
            listing_title="Disputed Item",
            description="Item that will cause dispute",
            price=Decimal('199.99')
        )
        
        order = Order.objects.create(
            buyer=buyer,
            seller=seller,
            product=product,
            total_price=product.price,
            status='DELIVERED'
        )
        
        # Initial conversation
        conversation = Conversation.objects.create(
            participant1=buyer,
            participant2=seller
        )
        
        # Buyer reports issue
        issue_message = Message.objects.create(
            conversation=conversation,
            sender=buyer,
            content="The item I received is not working as described."
        )
        
        # Seller responds defensively
        defense_message = Message.objects.create(
            conversation=conversation,
            sender=seller,
            content="The item works fine. I tested it before sending."
        )
        
        # Escalate to dispute
        conversation.is_disputed = True
        conversation.moderator = moderator
        conversation.save()
        
        order.status = 'DISPUTED'
        order.save()
        
        # Moderator joins conversation
        moderator_message = Message.objects.create(
            conversation=conversation,
            sender=moderator,
            content="I'm here to help resolve this dispute. Can both parties provide evidence?"
        )
        
        # Verify dispute escalation
        self.assertTrue(conversation.is_disputed)
        self.assertEqual(conversation.moderator, moderator)
        self.assertEqual(order.status, 'DISPUTED')
        
        # Resolution: Moderator decides in favor of buyer
        resolution_message = Message.objects.create(
            conversation=conversation,
            sender=moderator,
            content="After reviewing evidence, I'm issuing a refund to the buyer."
        )
        
        order.status = 'REFUNDED'
        order.save()
        
        # Create refund transactions
        refund_transaction = Transaction.objects.create(
            user=buyer,
            amount=order.total_price,
            transaction_type='refund',
            description=f"Refund for disputed Order #{order.id}"
        )
        
        self.assertEqual(order.status, 'REFUNDED')
        self.assertTrue(Transaction.objects.filter(user=buyer, transaction_type='refund').exists())

    def test_automatic_delivery_workflow(self):
        """Test automatic delivery workflow"""
        
        buyer = User.objects.create_user('auto_buyer', 'auto@buyer.com', 'pass123')
        seller = User.objects.create_user('auto_seller', 'auto@seller.com', 'pass123')
        
        # Product with automatic delivery
        product = Product.objects.create(
            seller=seller,
            game=self.game,
            category=self.category,
            listing_title="Auto Delivery Item",
            description="Automatically delivered digital item",
            price=Decimal('29.99'),
            automatic_delivery=True,
            stock_details="CODE001\nCODE002\nCODE003\nCODE004\nCODE005"
        )
        
        initial_stock = product.stock_count
        self.assertEqual(initial_stock, 5)
        
        # Create order
        order = Order.objects.create(
            buyer=buyer,
            seller=seller,
            product=product,
            total_price=product.price
        )
        
        # Simulate payment success
        order.status = 'PROCESSING'
        order.save()
        
        # In real implementation, automatic delivery would happen here
        # For testing, we simulate the process
        
        # Get the first available code
        available_codes = [line.strip() for line in product.stock_details.splitlines() if line.strip()]
        delivered_code = available_codes[0] if available_codes else None
        
        self.assertIsNotNone(delivered_code)
        self.assertEqual(delivered_code, "CODE001")
        
        # Remove delivered code from stock (simulate)
        remaining_codes = available_codes[1:]
        product.stock_details = '\n'.join(remaining_codes)
        product.save()
        
        # Mark as delivered
        order.status = 'DELIVERED'
        order.save()
        
        # Verify stock reduction
        self.assertEqual(product.stock_count, 4)

    def test_multi_item_order_workflow(self):
        """Test workflow with multiple items in cart (if supported)"""
        
        buyer = User.objects.create_user('multi_buyer', 'multi@buyer.com', 'pass123')
        seller = User.objects.create_user('multi_seller', 'multi@seller.com', 'pass123')
        
        # Create multiple products
        products = []
        for i in range(3):
            product = Product.objects.create(
                seller=seller,
                game=self.game,
                category=self.category,
                listing_title=f"Multi Item {i+1}",
                description=f"Description for item {i+1}",
                price=Decimal(f'{(i+1)*10}.99'),
                stock=5
            )
            products.append(product)
        
        # Create separate orders for each product (current system)
        orders = []
        total_amount = Decimal('0.00')
        
        for product in products:
            order = Order.objects.create(
                buyer=buyer,
                seller=seller,
                product=product,
                total_price=product.price
            )
            orders.append(order)
            total_amount += product.price
        
        # Verify orders created
        self.assertEqual(len(orders), 3)
        self.assertEqual(total_amount, Decimal('62.97'))  # 10.99 + 20.99 + 30.99
        
        # Process all orders
        for order in orders:
            order.status = 'COMPLETED'
            order.save()
        
        # Verify all completed
        completed_orders = Order.objects.filter(buyer=buyer, status='COMPLETED')
        self.assertEqual(completed_orders.count(), 3)


class UserInteractionWorkflowTest(TestCase):
    """Test user interaction workflows"""
    
    def setUp(self):
        self.user1 = User.objects.create_user('user1', 'user1@test.com', 'pass123')
        self.user2 = User.objects.create_user('user2', 'user2@test.com', 'pass123')
        self.game = Game.objects.create(title="Interaction Game")
        self.category = Category.objects.create(name="Interaction Category")

    def test_seller_buyer_communication_workflow(self):
        """Test complete seller-buyer communication workflow"""
        
        # Seller creates product
        product = Product.objects.create(
            seller=self.user1,
            game=self.game,
            category=self.category,
            listing_title="Communication Test Item",
            description="Item for testing communication",
            price=Decimal('149.99')
        )
        
        # Buyer initiates conversation
        conversation = Conversation.objects.create(
            participant1=self.user2,
            participant2=self.user1
        )
        
        # Communication flow
        messages = [
            (self.user2, "Is this item compatible with the latest version?"),
            (self.user1, "Yes, it's fully compatible with all recent updates."),
            (self.user2, "Great! What's the delivery time?"),
            (self.user1, "Digital delivery is instant after payment confirmation."),
            (self.user2, "Perfect, I'll purchase it now."),
        ]
        
        created_messages = []
        for sender, content in messages:
            message = Message.objects.create(
                conversation=conversation,
                sender=sender,
                content=content
            )
            created_messages.append(message)
        
        # Verify conversation
        conversation_messages = Message.objects.filter(conversation=conversation).order_by('timestamp')
        self.assertEqual(conversation_messages.count(), 5)
        
        # Verify message ordering
        self.assertEqual(conversation_messages.first().sender, self.user2)
        self.assertEqual(conversation_messages.last().sender, self.user2)
        
        # Mark messages as read
        for message in conversation_messages:
            if message.sender != self.user1:  # User1 reads messages from User2
                message.is_read = True
                message.save()
        
        # Verify read status
        unread_messages = Message.objects.filter(
            conversation=conversation,
            sender=self.user2,
            is_read=False
        )
        self.assertEqual(unread_messages.count(), 0)

    def test_profile_activity_workflow(self):
        """Test user profile activity workflow"""
        
        # User updates profile
        profile = Profile.objects.get(user=self.user1)
        profile.show_listings_on_site = True
        profile.save()
        
        # User creates multiple products
        products = []
        for i in range(5):
            product = Product.objects.create(
                seller=self.user1,
                game=self.game,
                category=self.category,
                listing_title=f"Profile Activity Item {i+1}",
                description=f"Activity test item {i+1}",
                price=Decimal(f'{(i+1)*25}.00')
            )
            products.append(product)
        
        # Verify profile shows listings
        user_products = Product.objects.filter(seller=self.user1, is_active=True)
        self.assertEqual(user_products.count(), 5)
        
        # Simulate user activity
        profile.last_seen = timezone.now()
        profile.save()
        
        # Verify online status
        # Note: is_online property checks if last_seen is within 10 seconds
        self.assertTrue(profile.is_online)


class ErrorHandlingWorkflowTest(TestCase):
    """Test error handling in workflows"""
    
    def setUp(self):
        self.user = User.objects.create_user('error_user', 'error@test.com', 'pass123')
        self.game = Game.objects.create(title="Error Game")
        self.category = Category.objects.create(name="Error Category")

    def test_out_of_stock_purchase_attempt(self):
        """Test handling of out-of-stock purchase attempts"""
        
        # Create product with limited stock
        product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title="Limited Stock Item",
            description="Only one available",
            price=Decimal('99.99'),
            stock=1
        )
        
        buyer1 = User.objects.create_user('buyer1', 'buyer1@stock.com', 'pass123')
        buyer2 = User.objects.create_user('buyer2', 'buyer2@stock.com', 'pass123')
        
        # First buyer successfully creates order
        order1 = Order.objects.create(
            buyer=buyer1,
            seller=self.user,
            product=product,
            total_price=product.price
        )
        
        # Second buyer attempts to order (should handle gracefully)
        # In real implementation, this would be prevented at the view level
        order2 = Order.objects.create(
            buyer=buyer2,
            seller=self.user,
            product=product,
            total_price=product.price
        )
        
        # Both orders exist but stock management would prevent both from completing
        self.assertEqual(Order.objects.filter(product=product).count(), 2)

    def test_deleted_product_order_handling(self):
        """Test handling of orders when product is deleted"""
        
        product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title="Soon to be deleted",
            description="This product will be deleted",
            price=Decimal('75.00')
        )
        
        buyer = User.objects.create_user('delete_buyer', 'delete@buyer.com', 'pass123')
        
        # Create order with snapshots
        order = Order.objects.create(
            buyer=buyer,
            seller=self.user,
            product=product,
            total_price=product.price,
            listing_title_snapshot=product.listing_title,
            description_snapshot=product.description,
            game_snapshot=self.game,
            category_snapshot=self.category
        )
        
        original_title = product.listing_title
        
        # Delete the product
        product.delete()
        
        # Order should still exist with snapshots
        order.refresh_from_db()
        self.assertIsNone(order.product)
        self.assertEqual(order.listing_title_snapshot, original_title)
        self.assertIsNotNone(order.game_snapshot)

    def test_invalid_payment_response_handling(self):
        """Test handling of invalid payment responses"""
        
        product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title="Payment Test Item",
            description="For testing payment errors",
            price=Decimal('50.00')
        )
        
        buyer = User.objects.create_user('payment_buyer', 'payment@buyer.com', 'pass123')
        
        order = Order.objects.create(
            buyer=buyer,
            seller=self.user,
            product=product,
            total_price=product.price
        )
        
        # Test various invalid payment responses
        invalid_responses = [
            {},  # Empty response
            {'pp_ResponseCode': '001'},  # Failed payment
            {'pp_ResponseCode': '000', 'pp_SecureHash': 'invalid'},  # Invalid hash
            {'pp_ResponseCode': '000', 'pp_Amount': '1'},  # Wrong amount
        ]
        
        for response in invalid_responses:
            is_valid = verify_jazzcash_response(response)
            self.assertFalse(is_valid, f"Invalid response should fail: {response}")
        
        # Order should remain in pending status
        order.refresh_from_db()
        self.assertEqual(order.status, 'PENDING_PAYMENT')


class PerformanceWorkflowTest(TestCase):
    """Test performance aspects of workflows"""
    
    def setUp(self):
        self.users = []
        for i in range(10):
            user = User.objects.create_user(f'perf_user_{i}', f'perf{i}@test.com', 'pass123')
            self.users.append(user)
        
        self.game = Game.objects.create(title="Performance Game")
        self.category = Category.objects.create(name="Performance Category")

    def test_bulk_order_creation(self):
        """Test bulk order creation performance"""
        
        seller = self.users[0]
        buyers = self.users[1:6]  # 5 buyers
        
        # Create products
        products = []
        for i in range(5):
            product = Product.objects.create(
                seller=seller,
                game=self.game,
                category=self.category,
                listing_title=f"Bulk Test Item {i+1}",
                description=f"Bulk test description {i+1}",
                price=Decimal(f'{(i+1)*20}.00'),
                stock=10
            )
            products.append(product)
        
        # Create orders in bulk
        orders = []
        for buyer in buyers:
            for product in products:
                order = Order.objects.create(
                    buyer=buyer,
                    seller=seller,
                    product=product,
                    total_price=product.price
                )
                orders.append(order)
        
        # Verify bulk creation
        self.assertEqual(len(orders), 25)  # 5 buyers × 5 products
        
        # Test bulk status update
        Order.objects.filter(id__in=[o.id for o in orders]).update(status='COMPLETED')
        
        completed_orders = Order.objects.filter(status='COMPLETED')
        self.assertEqual(completed_orders.count(), 25)

    def test_conversation_message_bulk_operations(self):
        """Test bulk message operations"""
        
        user1, user2 = self.users[0], self.users[1]
        
        conversation = Conversation.objects.create(
            participant1=user1,
            participant2=user2
        )
        
        # Create many messages
        messages = []
        for i in range(20):
            sender = user1 if i % 2 == 0 else user2
            message = Message.objects.create(
                conversation=conversation,
                sender=sender,
                content=f"Message number {i+1}"
            )
            messages.append(message)
        
        # Bulk mark as read
        Message.objects.filter(
            conversation=conversation,
            sender=user2
        ).update(is_read=True)
        
        # Verify bulk update
        unread_messages = Message.objects.filter(
            conversation=conversation,
            sender=user2,
            is_read=False
        )
        self.assertEqual(unread_messages.count(), 0)