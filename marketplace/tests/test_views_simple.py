from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal

from marketplace.models import Game, Category, Product, Order


class SimpleViewsTest(TestCase):
    """Simplified view tests focusing on model operations"""
    
    def setUp(self):
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

    def test_product_model_operations(self):
        """Test that product model operations work correctly"""
        # Test product creation
        self.assertEqual(self.product.listing_title, "Test Product")
        self.assertEqual(self.product.price, Decimal('99.99'))
        self.assertEqual(self.product.stock, 10)
        self.assertTrue(self.product.is_active)
        
        # Test product retrieval
        retrieved_product = Product.objects.get(id=self.product.id)
        self.assertEqual(retrieved_product.listing_title, "Test Product")

    def test_order_model_operations(self):
        """Test that order model operations work correctly"""
        buyer = User.objects.create_user('buyer', 'buyer@test.com', 'pass123')
        
        # Test order creation
        order = Order.objects.create(
            buyer=buyer,
            seller=self.user,
            product=self.product,
            total_price=self.product.price
        )
        
        self.assertEqual(order.buyer, buyer)
        self.assertEqual(order.seller, self.user)
        self.assertEqual(order.product, self.product)
        self.assertEqual(order.total_price, Decimal('99.99'))
        self.assertEqual(order.status, 'PENDING_PAYMENT')

    def test_user_profile_relationship(self):
        """Test that user profile relationships work correctly"""
        from marketplace.models import Profile
        
        # Profile should be created automatically
        profile = Profile.objects.get(user=self.user)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.user, self.user)

    def test_game_category_relationships(self):
        """Test that game and category relationships work correctly"""
        # Test that product is linked to game and category
        self.assertEqual(self.product.game, self.game)
        self.assertEqual(self.product.category, self.category)
        
        # Test that we can find products by game
        products_in_game = Product.objects.filter(game=self.game)
        self.assertIn(self.product, products_in_game)

    def test_product_active_filtering(self):
        """Test that product active filtering works correctly"""
        # All active products should include our product
        active_products = Product.objects.active()
        self.assertIn(self.product, active_products)
        
        # Deactivate product
        self.product.is_active = False
        self.product.save()
        
        # Should no longer be in active products
        active_products = Product.objects.active()
        self.assertNotIn(self.product, active_products)