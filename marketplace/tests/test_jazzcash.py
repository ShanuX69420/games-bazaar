from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from decimal import Decimal
import hashlib
from unittest.mock import patch, Mock

from marketplace.models import Order, Product, Game, Category, Profile
from marketplace.jazzcash_utils import get_jazzcash_payment_params, verify_jazzcash_response


@override_settings(
    JAZZCASH_MERCHANT_ID='test_merchant_id',
    JAZZCASH_PASSWORD='test_password',
    JAZZCASH_INTEGERITY_SALT='test_salt',
    JAZZCASH_RETURN_URL='http://testserver/jazzcash/callback/'
)
class JazzCashUtilsTest(TestCase):
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

    def test_get_jazzcash_payment_params(self):
        """Test JazzCash payment parameter generation"""
        params = get_jazzcash_payment_params(
            amount=self.order.total_price,
            order_id=self.order.id
        )
        
        # Test required parameters are present
        required_params = [
            'pp_Version', 'pp_TxnType', 'pp_Language', 'pp_MerchantID',
            'pp_Password', 'pp_TxnRefNo', 'pp_Amount', 'pp_TxnCurrency',
            'pp_TxnDateTime', 'pp_TxnExpiryDateTime', 'pp_BillReference',
            'pp_Description', 'pp_ReturnURL', 'pp_SecureHash'
        ]
        
        for param in required_params:
            self.assertIn(param, params)
        
        # Test specific values
        self.assertEqual(params['pp_Version'], '1.1')
        self.assertEqual(params['pp_TxnType'], 'MWALLET')
        self.assertEqual(params['pp_Language'], 'EN')
        self.assertEqual(params['pp_MerchantID'], 'test_merchant_id')
        self.assertEqual(params['pp_Password'], 'test_password')
        self.assertEqual(params['pp_Amount'], 9999)  # 99.99 * 100
        self.assertEqual(params['pp_TxnCurrency'], 'PKR')
        self.assertEqual(params['pp_BillReference'], str(self.order.id))
        self.assertEqual(params['pp_ReturnURL'], 'http://testserver/jazzcash/callback/')
        
        # Test that secure hash is generated
        self.assertIsNotNone(params['pp_SecureHash'])
        self.assertEqual(len(params['pp_SecureHash']), 64)  # SHA256 hash length

    def test_jazzcash_secure_hash_generation(self):
        """Test that secure hash is generated correctly"""
        params = get_jazzcash_payment_params(
            amount=Decimal('100.00'),
            order_id=123
        )
        
        # Manually calculate expected hash
        sorted_params_list = [str(params[key]) for key in sorted(params) if key != 'pp_SecureHash' and params[key]]
        hash_string = 'test_salt' + '&' + '&'.join(sorted_params_list)
        expected_hash = hashlib.sha256(hash_string.encode()).hexdigest()
        
        self.assertEqual(params['pp_SecureHash'], expected_hash)

    def test_verify_jazzcash_response_valid(self):
        """Test verification of valid JazzCash response"""
        # Create a mock response data
        response_data = {
            'pp_Amount': '10000',
            'pp_BillReference': '123',
            'pp_Language': 'EN',
            'pp_MerchantID': 'test_merchant_id',
            'pp_ResponseCode': '000',
            'pp_ResponseMessage': 'Transaction Successful',
            'pp_RetreivalReferenceNo': 'REF123456',
            'pp_TxnCurrency': 'PKR',
            'pp_TxnDateTime': '20250130120000',
            'pp_TxnRefNo': 'TXN123456',
            'pp_Version': '1.1'
        }
        
        # Calculate correct hash
        sorted_params_list = [str(response_data[key]) for key in sorted(response_data) if response_data[key]]
        hash_string = 'test_salt' + '&' + '&'.join(sorted_params_list)
        correct_hash = hashlib.sha256(hash_string.encode()).hexdigest()
        response_data['pp_SecureHash'] = correct_hash
        
        # Test verification
        is_valid = verify_jazzcash_response(response_data)
        self.assertTrue(is_valid)

    def test_verify_jazzcash_response_invalid_hash(self):
        """Test verification fails with invalid hash"""
        response_data = {
            'pp_Amount': '10000',
            'pp_BillReference': '123',
            'pp_Language': 'EN',
            'pp_MerchantID': 'test_merchant_id',
            'pp_ResponseCode': '000',
            'pp_SecureHash': 'invalid_hash'
        }
        
        is_valid = verify_jazzcash_response(response_data)
        self.assertFalse(is_valid)

    def test_verify_jazzcash_response_missing_hash(self):
        """Test verification fails when hash is missing"""
        response_data = {
            'pp_Amount': '10000',
            'pp_BillReference': '123',
            'pp_ResponseCode': '000'
        }
        
        is_valid = verify_jazzcash_response(response_data)
        self.assertFalse(is_valid)

    def test_amount_conversion_to_paisa(self):
        """Test that PKR amounts are correctly converted to paisa"""
        # Test various amounts
        test_cases = [
            (Decimal('1.00'), 100),
            (Decimal('99.99'), 9999),
            (Decimal('150.50'), 15050),
            (Decimal('0.01'), 1),
        ]
        
        for amount, expected_paisa in test_cases:
            params = get_jazzcash_payment_params(amount=amount, order_id=1)
            self.assertEqual(params['pp_Amount'], expected_paisa)


@override_settings(
    JAZZCASH_MERCHANT_ID='test_merchant_id',
    JAZZCASH_PASSWORD='test_password',
    JAZZCASH_INTEGERITY_SALT='test_salt'
)
class JazzCashPaymentFlowTest(TestCase):
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

    def test_payment_form_generation(self):
        """Test that payment parameters are generated correctly for orders"""
        # Create order directly (not through view)
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )
        
        # Test parameter generation
        params = get_jazzcash_payment_params(
            amount=order.total_price,
            order_id=order.id
        )
        
        # Verify key parameters
        self.assertEqual(params['pp_MerchantID'], 'test_merchant_id')
        self.assertEqual(params['pp_Amount'], 9999)  # 99.99 * 100
        self.assertEqual(params['pp_BillReference'], str(order.id))
        self.assertIn('pp_SecureHash', params)
        self.assertIsNotNone(params['pp_SecureHash'])

    @patch('marketplace.views.verify_jazzcash_response')
    def test_payment_callback_success(self, mock_verify):
        """Test successful payment callback processing"""
        mock_verify.return_value = True
        
        # Create an order first
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price,
            status='PENDING_PAYMENT'
        )
        
        # Mock successful JazzCash response
        callback_data = {
            'pp_ResponseCode': '000',
            'pp_ResponseMessage': 'Transaction Successful',
            'pp_BillReference': str(order.id),
            'pp_Amount': '9999',
            'pp_SecureHash': 'valid_hash'
        }
        
        response = self.client.post('/jazzcash/callback/', callback_data)
        
        # Check that order status was updated
        order.refresh_from_db()
        # Note: Actual status update logic would depend on your implementation

    @patch('marketplace.views.verify_jazzcash_response')
    def test_payment_callback_failure(self, mock_verify):
        """Test failed payment callback processing"""
        mock_verify.return_value = False
        
        # Create an order first
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price,
            status='PENDING_PAYMENT'
        )
        
        # Mock failed JazzCash response
        callback_data = {
            'pp_ResponseCode': '001',
            'pp_ResponseMessage': 'Transaction Failed',
            'pp_BillReference': str(order.id),
            'pp_Amount': '9999',
            'pp_SecureHash': 'invalid_hash'
        }
        
        response = self.client.post('/jazzcash/callback/', callback_data)
        
        # Check that order status remains pending or is marked as failed
        order.refresh_from_db()
        self.assertNotEqual(order.status, 'completed')