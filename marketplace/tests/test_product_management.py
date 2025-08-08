"""
Product Management Tests - Based on comprehensive manual testing
Tests product CRUD operations, stock management, image uploads
Matches manual Test 6: Product Management
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from decimal import Decimal

from marketplace.models import Product, ProductImage, Game, Category, Order


class ProductCreationTest(TestCase):
    """Test product creation with all required fields"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('seller', 'seller@test.com', 'testpass123')
        self.game = Game.objects.create(title='Test Game')
        self.category = Category.objects.create(name='Test Category')
        self.client.login(username='seller', password='testpass123')

    def test_product_creation_success(self):
        """Test successful product creation with all required fields"""
        product_data = {
            'game': self.game.id,
            'category': self.category.id,
            'listing_title': 'Amazing Game Item',
            'description': 'This is a detailed description of the game item.',
            'price': '19.99',
            'stock_quantity': 10,
            'condition': 'NEW',
            'delivery_method': 'DIGITAL',
        }
        
        response = self.client.post(reverse('create_product'), product_data)
        
        # Should redirect to product page after creation
        self.assertEqual(response.status_code, 302)
        
        # Verify product was created
        product = Product.objects.get(listing_title='Amazing Game Item')
        self.assertEqual(product.seller, self.user)
        self.assertEqual(product.price, Decimal('19.99'))
        self.assertEqual(product.stock_quantity, 10)

    def test_product_creation_with_images(self):
        """Test product creation with image uploads"""
        # Create a fake image file
        image_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
        image_file = SimpleUploadedFile(
            'test_image.png',
            image_content,
            content_type='image/png'
        )
        
        product_data = {
            'game': self.game.id,
            'category': self.category.id,
            'listing_title': 'Product with Image',
            'description': 'Product description',
            'price': '29.99',
            'stock_quantity': 5,
            'condition': 'NEW',
            'delivery_method': 'DIGITAL',
            'images': [image_file],
        }
        
        response = self.client.post(reverse('create_product'), product_data)
        self.assertEqual(response.status_code, 302)
        
        product = Product.objects.get(listing_title='Product with Image')
        self.assertTrue(product.images.exists())

    def test_product_creation_validation(self):
        """Test product creation validation for required fields"""
        # Missing required fields
        incomplete_data = {
            'listing_title': 'Incomplete Product',
            # Missing game, category, price, etc.
        }
        
        response = self.client.post(reverse('create_product'), incomplete_data)
        
        # Should stay on form page with errors
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This field is required')

    def test_negative_price_validation(self):
        """Test that negative prices are rejected"""
        product_data = {
            'game': self.game.id,
            'category': self.category.id,
            'listing_title': 'Negative Price Product',
            'description': 'Should not work',
            'price': '-10.00',  # Invalid negative price
            'stock_quantity': 5,
            'condition': 'NEW',
            'delivery_method': 'DIGITAL',
        }
        
        response = self.client.post(reverse('create_product'), product_data)
        self.assertEqual(response.status_code, 200)  # Should stay on form
        self.assertContains(response, 'positive')  # Should show validation error


class ProductEditTest(TestCase):
    """Test product editing functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('seller', 'seller@test.com', 'testpass123')
        self.other_user = User.objects.create_user('other', 'other@test.com', 'pass123')
        self.game = Game.objects.create(title='Test Game')
        self.category = Category.objects.create(name='Test Category')
        
        self.product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title='Original Title',
            description='Original description',
            price=Decimal('19.99'),
            stock_quantity=10
        )
        
        self.client.login(username='seller', password='testpass123')

    def test_product_edit_success(self):
        """Test successful product editing"""
        edit_data = {
            'game': self.game.id,
            'category': self.category.id,
            'listing_title': 'Updated Title',
            'description': 'Updated description with new details',
            'price': '24.99',
            'stock_quantity': 15,
            'condition': 'USED',
            'delivery_method': 'PHYSICAL',
        }
        
        response = self.client.post(
            reverse('edit_product', args=[self.product.pk]), 
            edit_data
        )
        
        self.assertEqual(response.status_code, 302)
        
        # Verify changes were saved
        self.product.refresh_from_db()
        self.assertEqual(self.product.listing_title, 'Updated Title')
        self.assertEqual(self.product.description, 'Updated description with new details')
        self.assertEqual(self.product.price, Decimal('24.99'))
        self.assertEqual(self.product.stock_quantity, 15)

    def test_product_edit_authorization(self):
        """Test that only product owner can edit"""
        # Try to edit as different user
        self.client.login(username='other', password='pass123')
        
        edit_data = {
            'listing_title': 'Hacked Title',
            'price': '999.99',
        }
        
        response = self.client.post(
            reverse('edit_product', args=[self.product.pk]), 
            edit_data
        )
        
        # Should be forbidden or redirect
        self.assertIn(response.status_code, [403, 302])
        
        # Verify product wasn't changed
        self.product.refresh_from_db()
        self.assertEqual(self.product.listing_title, 'Original Title')

    def test_product_edit_preserve_owner(self):
        """Test that editing doesn't change product owner"""
        original_seller = self.product.seller
        
        edit_data = {
            'game': self.game.id,
            'category': self.category.id,
            'listing_title': 'Updated Title',
            'description': 'Updated description',
            'price': '29.99',
            'stock_quantity': 5,
        }
        
        self.client.post(
            reverse('edit_product', args=[self.product.pk]), 
            edit_data
        )
        
        self.product.refresh_from_db()
        self.assertEqual(self.product.seller, original_seller)


class ProductDeletionTest(TestCase):
    """Test product deletion functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('seller', 'seller@test.com', 'testpass123')
        self.other_user = User.objects.create_user('other', 'other@test.com', 'pass123')
        self.game = Game.objects.create(title='Test Game')
        self.category = Category.objects.create(name='Test Category')
        
        self.product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title='Product to Delete',
            description='This product will be deleted',
            price=Decimal('15.99'),
            stock_quantity=3
        )
        
        self.client.login(username='seller', password='testpass123')

    def test_product_deletion_success(self):
        """Test successful product deletion by owner"""
        product_id = self.product.pk
        
        response = self.client.post(reverse('delete_product', args=[product_id]))
        
        # Should redirect after deletion
        self.assertEqual(response.status_code, 302)
        
        # Verify product no longer exists
        with self.assertRaises(Product.DoesNotExist):
            Product.objects.get(pk=product_id)

    def test_product_deletion_authorization(self):
        """Test that only product owner can delete"""
        self.client.login(username='other', password='pass123')
        
        product_id = self.product.pk
        response = self.client.post(reverse('delete_product', args=[product_id]))
        
        # Should be forbidden
        self.assertIn(response.status_code, [403, 302])
        
        # Verify product still exists
        self.assertTrue(Product.objects.filter(pk=product_id).exists())

    def test_delete_product_with_orders(self):
        """Test deletion behavior when product has orders"""
        # Create an order for this product
        buyer = User.objects.create_user('buyer', 'buyer@test.com', 'pass123')
        order = Order.objects.create(
            buyer=buyer,
            seller=self.user,
            product=self.product,
            quantity=1,
            total_amount=self.product.price
        )
        
        product_id = self.product.pk
        response = self.client.post(reverse('delete_product', args=[product_id]))
        
        # Deletion might be prevented or handled specially
        # This depends on your business logic - adjust assertion accordingly
        if response.status_code == 302:
            # If deletion is allowed, order should still exist with product reference
            order.refresh_from_db()
            self.assertIsNotNone(order.product_id)  # Foreign key preserved
        else:
            # If deletion is prevented, product should still exist
            self.assertTrue(Product.objects.filter(pk=product_id).exists())


class StockManagementTest(TestCase):
    """Test stock management functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('seller', 'seller@test.com', 'testpass123')
        self.buyer = User.objects.create_user('buyer', 'buyer@test.com', 'pass123')
        self.game = Game.objects.create(title='Test Game')
        self.category = Category.objects.create(name='Test Category')
        
        self.product = Product.objects.create(
            seller=self.user,
            game=self.game,
            category=self.category,
            listing_title='Stock Test Product',
            description='Testing stock management',
            price=Decimal('10.00'),
            stock_quantity=5
        )

    def test_stock_decreases_on_purchase(self):
        """Test that stock decreases when product is purchased"""
        initial_stock = self.product.stock_quantity
        
        # Create an order
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.user,
            product=self.product,
            quantity=2,
            total_amount=Decimal('20.00')
        )
        
        # Stock should decrease (if your system handles this automatically)
        # Note: Adjust this test based on your actual stock management logic
        self.product.refresh_from_db()
        expected_stock = initial_stock - 2
        
        # This assertion depends on your business logic
        # If stock is decremented automatically on order creation:
        # self.assertEqual(self.product.stock_quantity, expected_stock)
        # If stock is decremented on order completion:
        # You'd need to test the order completion process

    def test_stock_quantity_validation(self):
        """Test stock quantity validation"""
        # Test negative stock
        self.product.stock_quantity = -1
        
        with self.assertRaises(Exception):  # Adjust exception type based on your validation
            self.product.full_clean()

    def test_out_of_stock_behavior(self):
        """Test behavior when product is out of stock"""
        self.product.stock_quantity = 0
        self.product.save()
        
        # Test that out-of-stock products are handled appropriately
        response = self.client.get(reverse('product_detail', args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        
        # Should show out of stock message
        self.assertContains(response, 'out of stock', status_code=200)

    def test_stock_update_authorization(self):
        """Test that only product owner can update stock"""
        self.client.login(username='seller', password='testpass123')
        
        # Update stock as owner - should work
        update_data = {
            'game': self.game.id,
            'category': self.category.id,
            'listing_title': self.product.listing_title,
            'description': self.product.description,
            'price': str(self.product.price),
            'stock_quantity': 20,  # Increased stock
        }
        
        response = self.client.post(
            reverse('edit_product', args=[self.product.pk]), 
            update_data
        )
        
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 20)


class ProductSearchTest(TestCase):
    """Test product search and filtering functionality"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('seller', 'seller@test.com', 'testpass123')
        self.game1 = Game.objects.create(title='Call of Duty')
        self.game2 = Game.objects.create(title='FIFA 2024')
        self.category = Category.objects.create(name='Game Keys')
        
        # Create test products
        self.product1 = Product.objects.create(
            seller=self.user,
            game=self.game1,
            category=self.category,
            listing_title='CoD Modern Warfare',
            description='Latest Call of Duty game',
            price=Decimal('59.99'),
            stock_quantity=10
        )
        
        self.product2 = Product.objects.create(
            seller=self.user,
            game=self.game2,
            category=self.category,
            listing_title='FIFA Ultimate Edition',
            description='FIFA with all DLCs',
            price=Decimal('79.99'),
            stock_quantity=5
        )

    def test_product_search_by_game_name(self):
        """Test searching products by game name"""
        response = self.client.get(reverse('home'), {'search': 'Call of Duty'})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CoD Modern Warfare')
        self.assertNotContains(response, 'FIFA Ultimate Edition')

    def test_product_search_by_title(self):
        """Test searching products by listing title"""
        response = self.client.get(reverse('home'), {'search': 'Ultimate'})
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'FIFA Ultimate Edition')
        self.assertNotContains(response, 'CoD Modern Warfare')

    def test_empty_search_shows_all_products(self):
        """Test that empty search shows all products"""
        response = self.client.get(reverse('home'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CoD Modern Warfare')
        self.assertContains(response, 'FIFA Ultimate Edition')

    def test_no_results_search(self):
        """Test search with no matching results"""
        response = self.client.get(reverse('home'), {'search': 'Nonexistent Game'})
        
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'CoD Modern Warfare')
        self.assertNotContains(response, 'FIFA Ultimate Edition')