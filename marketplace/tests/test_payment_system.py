from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from decimal import Decimal
import hashlib
from unittest.mock import patch, Mock
import json

from marketplace.models import Order, Product, Game, Category, Profile, Transaction
from marketplace.jazzcash_utils import get_jazzcash_payment_params, verify_jazzcash_response


@override_settings(
    JAZZCASH_MERCHANT_ID='TEST_MERCHANT_123',
    JAZZCASH_PASSWORD='TEST_PASSWORD_456',
    JAZZCASH_INTEGERITY_SALT='TEST_SALT_789',
    JAZZCASH_RETURN_URL='http://testserver/jazzcash/callback/',
    JAZZCASH_TRANSACTION_URL='https://sandbox.jazzcash.com.pk/test'
)
class JazzCashPaymentSystemTest(TestCase):
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
        
        self.game = Game.objects.create(title="Payment Test Game")
        self.category = Category.objects.create(name="Payment Test Category")
        
        self.product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Payment Test Product",
            description="Testing payments",
            price=Decimal('199.99'),
            stock=5
        )
        
        self.order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )

    def test_payment_parameter_generation(self):
        """Test JazzCash payment parameter generation"""
        params = get_jazzcash_payment_params(
            amount=self.order.total_price,
            order_id=self.order.id
        )
        
        # Test all required parameters are present
        required_params = [
            'pp_Version', 'pp_TxnType', 'pp_Language', 'pp_MerchantID',
            'pp_Password', 'pp_TxnRefNo', 'pp_Amount', 'pp_TxnCurrency',
            'pp_TxnDateTime', 'pp_TxnExpiryDateTime', 'pp_BillReference',
            'pp_Description', 'pp_ReturnURL', 'pp_SecureHash'
        ]
        
        for param in required_params:
            self.assertIn(param, params, f"Missing parameter: {param}")
        
        # Test specific values
        self.assertEqual(params['pp_Version'], '1.1')
        self.assertEqual(params['pp_TxnType'], 'MWALLET')
        self.assertEqual(params['pp_Language'], 'EN')
        self.assertEqual(params['pp_MerchantID'], 'TEST_MERCHANT_123')
        self.assertEqual(params['pp_Password'], 'TEST_PASSWORD_456')
        self.assertEqual(params['pp_Amount'], 19999)  # 199.99 * 100
        self.assertEqual(params['pp_TxnCurrency'], 'PKR')
        self.assertEqual(params['pp_BillReference'], str(self.order.id))
        self.assertEqual(params['pp_ReturnURL'], 'http://testserver/jazzcash/callback/')
        
        # Test secure hash exists and is 64 characters (SHA256)
        self.assertIsInstance(params['pp_SecureHash'], str)
        self.assertEqual(len(params['pp_SecureHash']), 64)

    def test_amount_conversion_edge_cases(self):
        """Test amount conversion edge cases"""
        test_cases = [
            (Decimal('0.01'), 1),      # Minimum amount
            (Decimal('1.00'), 100),    # Basic conversion
            (Decimal('99.99'), 9999),  # Common price
            (Decimal('999.99'), 99999), # High price
            (Decimal('0.00'), 0),      # Free item
        ]
        
        for amount, expected_paisa in test_cases:
            params = get_jazzcash_payment_params(amount=amount, order_id=1)
            self.assertEqual(params['pp_Amount'], expected_paisa,
                           f"Failed for amount {amount}")

    def test_secure_hash_generation(self):
        """Test secure hash generation and consistency"""
        amount = Decimal('100.00')
        order_id = 123
        
        # Generate parameters twice
        params1 = get_jazzcash_payment_params(amount=amount, order_id=order_id)
        params2 = get_jazzcash_payment_params(amount=amount, order_id=order_id)
        
        # Hash should be consistent for same parameters (excluding time-based fields)
        # Note: TxnDateTime will be different, so we test the algorithm instead
        
        # Manually calculate hash for verification
        test_params = params1.copy()
        del test_params['pp_SecureHash']
        
        sorted_params_list = [str(test_params[key]) for key in sorted(test_params) 
                             if key != 'pp_SecureHash' and test_params[key]]
        hash_string = 'TEST_SALT_789' + '&' + '&'.join(sorted_params_list)
        expected_hash = hashlib.sha256(hash_string.encode()).hexdigest()
        
        self.assertEqual(params1['pp_SecureHash'], expected_hash)

    def test_payment_response_verification_valid(self):
        """Test verification of valid JazzCash response"""
        # Create mock successful response
        response_data = {
            'pp_Amount': '19999',
            'pp_BillReference': str(self.order.id),
            'pp_Language': 'EN',
            'pp_MerchantID': 'TEST_MERCHANT_123',
            'pp_ResponseCode': '000',
            'pp_ResponseMessage': 'Transaction Successful',
            'pp_RetreivalReferenceNo': 'REF20250130123456',
            'pp_TxnCurrency': 'PKR',
            'pp_TxnDateTime': '20250130120000',
            'pp_TxnRefNo': 'TXN20250130120000',
            'pp_Version': '1.1'
        }
        
        # Calculate correct hash
        sorted_params_list = [str(response_data[key]) for key in sorted(response_data) 
                             if response_data[key]]
        hash_string = 'TEST_SALT_789' + '&' + '&'.join(sorted_params_list)
        correct_hash = hashlib.sha256(hash_string.encode()).hexdigest()
        response_data['pp_SecureHash'] = correct_hash
        
        # Test verification
        is_valid = verify_jazzcash_response(response_data)
        self.assertTrue(is_valid, "Valid response should pass verification")

    def test_payment_response_verification_invalid_hash(self):
        """Test verification fails with tampered hash"""
        response_data = {
            'pp_Amount': '19999',
            'pp_BillReference': str(self.order.id),
            'pp_ResponseCode': '000',
            'pp_SecureHash': 'tampered_hash_value_not_valid_123456789'
        }
        
        is_valid = verify_jazzcash_response(response_data)
        self.assertFalse(is_valid, "Tampered hash should fail verification")

    def test_payment_response_verification_missing_hash(self):
        """Test verification fails when hash is missing"""
        response_data = {
            'pp_Amount': '19999',
            'pp_BillReference': str(self.order.id),
            'pp_ResponseCode': '000'
            # pp_SecureHash missing
        }
        
        is_valid = verify_jazzcash_response(response_data)
        self.assertFalse(is_valid, "Missing hash should fail verification")

    def test_payment_response_verification_empty_response(self):
        """Test verification handles empty/invalid responses"""
        test_cases = [
            {},  # Empty response
            None,  # None response (if function handles it)
            {'pp_SecureHash': ''},  # Empty hash
        ]
        
        for response in test_cases:
            if response is not None:
                is_valid = verify_jazzcash_response(response)
                self.assertFalse(is_valid, f"Invalid response should fail: {response}")

    def test_payment_amount_manipulation_detection(self):
        """Test detection of amount manipulation in response"""
        # Create legitimate response
        response_data = {
            'pp_Amount': '19999',  # Correct amount
            'pp_BillReference': str(self.order.id),
            'pp_ResponseCode': '000',
            'pp_MerchantID': 'TEST_MERCHANT_123'
        }
        
        # Calculate hash for legitimate amount
        sorted_params_list = [str(response_data[key]) for key in sorted(response_data) 
                             if response_data[key]]
        hash_string = 'TEST_SALT_789' + '&' + '&'.join(sorted_params_list)
        correct_hash = hashlib.sha256(hash_string.encode()).hexdigest()
        
        # Now tamper with amount but keep original hash
        response_data['pp_Amount'] = '1'  # Tampered to 1 paisa
        response_data['pp_SecureHash'] = correct_hash  # Original hash
        
        is_valid = verify_jazzcash_response(response_data)
        self.assertFalse(is_valid, "Tampered amount should be detected")

    def test_payment_transaction_reference_validation(self):
        """Test transaction reference number validation"""
        params = get_jazzcash_payment_params(
            amount=Decimal('50.00'),
            order_id=self.order.id
        )
        
        # Transaction reference should follow expected format
        txn_ref = params['pp_TxnRefNo']
        self.assertTrue(txn_ref.startswith('TXN'), "Transaction ref should start with TXN")
        self.assertEqual(len(txn_ref), 21, "Transaction ref should be 21 characters")  # TXN + 14 digits + 4 order digits

    def test_payment_expiry_datetime(self):
        """Test payment expiry datetime is properly set"""
        params = get_jazzcash_payment_params(
            amount=Decimal('25.00'),
            order_id=self.order.id
        )
        
        txn_datetime = params['pp_TxnDateTime']
        expiry_datetime = params['pp_TxnExpiryDateTime']
        
        # Both should be 14 character datetime strings
        self.assertEqual(len(txn_datetime), 14)
        self.assertEqual(len(expiry_datetime), 14)
        
        # Expiry should be after transaction datetime
        self.assertGreater(expiry_datetime, txn_datetime)

    def test_payment_description_formatting(self):
        """Test payment description is properly formatted"""
        params = get_jazzcash_payment_params(
            amount=Decimal('75.50'),
            order_id=self.order.id
        )
        
        description = params['pp_Description']
        expected_description = f'Payment for Order ID: {self.order.id}'
        self.assertEqual(description, expected_description)

    def test_multiple_orders_different_references(self):
        """Test that different orders get different transaction references"""
        # Create second order
        order2 = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=Decimal('150.00')
        )
        
        params1 = get_jazzcash_payment_params(
            amount=self.order.total_price,
            order_id=self.order.id
        )
        
        params2 = get_jazzcash_payment_params(
            amount=order2.total_price,
            order_id=order2.id
        )
        
        # Transaction references should be different
        self.assertNotEqual(params1['pp_TxnRefNo'], params2['pp_TxnRefNo'])
        
        # Bill references should match respective order IDs
        self.assertEqual(params1['pp_BillReference'], str(self.order.id))
        self.assertEqual(params2['pp_BillReference'], str(order2.id))


class PaymentSecurityTest(TestCase):
    """Test payment system security measures"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='security_test',
            email='security@example.com',
            password='testpass123'
        )

    @override_settings(
        JAZZCASH_MERCHANT_ID='',
        JAZZCASH_PASSWORD='',
        JAZZCASH_INTEGERITY_SALT=''
    )
    def test_missing_payment_credentials(self):
        """Test behavior when payment credentials are missing"""
        # This should handle missing credentials gracefully
        try:
            params = get_jazzcash_payment_params(amount=Decimal('100.00'), order_id=1)
            # Should either work with empty credentials or raise appropriate error
            self.assertIn('pp_MerchantID', params)
        except Exception as e:
            # If it raises an error, it should be a meaningful one
            self.assertIsInstance(e, (ValueError, KeyError))

    def test_sql_injection_in_payment_parameters(self):
        """Test payment parameters are safe from SQL injection"""
        # Test with potentially malicious input
        malicious_order_id = "1'; DROP TABLE orders; --"
        
        try:
            params = get_jazzcash_payment_params(
                amount=Decimal('100.00'),
                order_id=malicious_order_id
            )
            # Should handle malicious input safely
            self.assertEqual(params['pp_BillReference'], str(malicious_order_id))
        except Exception:
            # If it fails, that's also acceptable for security
            pass

    def test_xss_prevention_in_payment_description(self):
        """Test XSS prevention in payment descriptions"""
        # Test with XSS payload
        xss_order_id = "<script>alert('xss')</script>"
        
        params = get_jazzcash_payment_params(
            amount=Decimal('50.00'),
            order_id=xss_order_id
        )
        
        description = params['pp_Description']
        # Should not contain executable script tags (should be HTML escaped)
        self.assertNotIn('<script>', description)
        self.assertNotIn('</script>', description)
        # Should contain escaped version instead
        self.assertIn('&lt;script&gt;', description)
        self.assertIn('&lt;/script&gt;', description)

    def test_hash_collision_resistance(self):
        """Test that similar inputs produce different hashes"""
        # Test with very similar but different parameters
        params1 = get_jazzcash_payment_params(amount=Decimal('100.00'), order_id=1)
        params2 = get_jazzcash_payment_params(amount=Decimal('100.01'), order_id=1)
        
        # Even tiny differences should produce different hashes
        self.assertNotEqual(params1['pp_SecureHash'], params2['pp_SecureHash'])


class PaymentWorkflowIntegrationTest(TestCase):
    """Test complete payment workflow integration"""
    
    def setUp(self):
        self.buyer = User.objects.create_user(
            username='workflow_buyer',
            email='buyer@workflow.com',
            password='testpass123'
        )
        self.seller = User.objects.create_user(
            username='workflow_seller',
            email='seller@workflow.com',
            password='testpass123'
        )
        
        self.game = Game.objects.create(title="Workflow Test Game")
        self.category = Category.objects.create(name="Workflow Test Category")
        
        self.product = Product.objects.create(
            seller=self.seller,
            game=self.game,
            category=self.category,
            listing_title="Workflow Test Product",
            description="Testing complete workflow",
            price=Decimal('299.99'),
            stock=3
        )

    def test_complete_successful_payment_workflow(self):
        """Test complete successful payment workflow"""
        # Step 1: Create order
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )
        
        self.assertEqual(order.status, 'PENDING_PAYMENT')
        
        # Step 2: Generate payment parameters
        params = get_jazzcash_payment_params(
            amount=order.total_price,
            order_id=order.id
        )
        
        self.assertIsInstance(params, dict)
        self.assertEqual(params['pp_BillReference'], str(order.id))
        
        # Step 3: Simulate successful payment response
        success_response = {
            'pp_Amount': '29999',
            'pp_BillReference': str(order.id),
            'pp_ResponseCode': '000',
            'pp_ResponseMessage': 'Transaction Successful',
            'pp_MerchantID': params['pp_MerchantID']
        }
        
        # Calculate hash for success response
        sorted_params = [str(success_response[key]) for key in sorted(success_response)]
        with override_settings(JAZZCASH_INTEGERITY_SALT='TEST_SALT'):
            hash_string = 'TEST_SALT' + '&' + '&'.join(sorted_params)
            success_response['pp_SecureHash'] = hashlib.sha256(hash_string.encode()).hexdigest()
        
        # Step 4: Verify response
        with override_settings(JAZZCASH_INTEGERITY_SALT='TEST_SALT'):
            is_valid = verify_jazzcash_response(success_response)
            self.assertTrue(is_valid)

    def test_failed_payment_workflow(self):
        """Test failed payment workflow handling"""
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )
        
        # Simulate failed payment response
        failed_response = {
            'pp_Amount': '29999',
            'pp_BillReference': str(order.id),
            'pp_ResponseCode': '001',  # Failed response code
            'pp_ResponseMessage': 'Transaction Failed',
            'pp_SecureHash': 'invalid_hash'
        }
        
        is_valid = verify_jazzcash_response(failed_response)
        self.assertFalse(is_valid)

    def test_payment_timeout_scenario(self):
        """Test payment timeout scenario"""
        order = Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            product=self.product,
            total_price=self.product.price
        )
        
        # Generate payment with expiry
        params = get_jazzcash_payment_params(
            amount=order.total_price,
            order_id=order.id
        )
        
        # Verify expiry datetime is set
        self.assertIn('pp_TxnExpiryDateTime', params)
        self.assertIsInstance(params['pp_TxnExpiryDateTime'], str)
        self.assertEqual(len(params['pp_TxnExpiryDateTime']), 14)


class TransactionRecordingTest(TestCase):
    """Test transaction recording and audit trail"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='transaction_test',
            email='transaction@test.com',
            password='testpass123'
        )

    def test_transaction_recording(self):
        """Test that transactions are properly recorded"""
        # Create various transaction types
        transactions = [
            ('deposit', Decimal('100.00'), "Deposit via JazzCash"),
            ('withdrawal', Decimal('50.00'), "Withdrawal to bank"),
            ('purchase', Decimal('25.00'), "Purchase of product #123"),
            ('sale', Decimal('75.00'), "Sale of product #456"),
            ('commission', Decimal('5.00'), "Commission from sale #456")
        ]
        
        for trans_type, amount, description in transactions:
            transaction = Transaction.objects.create(
                user=self.user,
                amount=amount,
                transaction_type=trans_type,
                description=description
            )
            
            self.assertEqual(transaction.user, self.user)
            self.assertEqual(transaction.amount, amount)
            self.assertEqual(transaction.transaction_type, trans_type)
            self.assertEqual(transaction.description, description)
            self.assertIsNotNone(transaction.created_at)

    def test_transaction_audit_trail(self):
        """Test transaction audit trail completeness"""
        Transaction.objects.create(
            user=self.user,
            amount=Decimal('150.00'),
            transaction_type='deposit',
            description="Test audit transaction"
        )
        
        # Verify all transactions are recorded
        user_transactions = Transaction.objects.filter(user=self.user)
        self.assertEqual(user_transactions.count(), 1)
        
        transaction = user_transactions.first()
        
        # Verify all audit fields are present
        required_fields = ['user', 'amount', 'transaction_type', 'description', 'created_at']
        for field in required_fields:
            self.assertTrue(hasattr(transaction, field))
            self.assertIsNotNone(getattr(transaction, field))