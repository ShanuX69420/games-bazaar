from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
import hashlib

from marketplace.jazzcash_utils import get_jazzcash_payment_params, verify_jazzcash_response


class JazzCashUtilityTest(TestCase):
    """Test JazzCash utility functions without Django views"""
    
    def test_payment_params_generation(self):
        """Test basic payment parameter generation"""
        with self.settings(
            JAZZCASH_MERCHANT_ID='test_merchant',
            JAZZCASH_PASSWORD='test_password',
            JAZZCASH_INTEGERITY_SALT='test_salt',
            JAZZCASH_RETURN_URL='http://test.com/callback/'
        ):
            params = get_jazzcash_payment_params(
                amount=Decimal('100.00'),
                order_id=123
            )
            
            # Test basic parameters
            self.assertEqual(params['pp_MerchantID'], 'test_merchant')
            self.assertEqual(params['pp_Password'], 'test_password')
            self.assertEqual(params['pp_Amount'], 10000)  # 100.00 * 100
            self.assertEqual(params['pp_BillReference'], '123')
            self.assertIn('pp_SecureHash', params)
            self.assertIsNotNone(params['pp_SecureHash'])

    def test_hash_verification_valid(self):
        """Test hash verification with valid data"""
        with self.settings(JAZZCASH_INTEGERITY_SALT='test_salt'):
            # Create test response data
            response_data = {
                'pp_Amount': '10000',
                'pp_BillReference': '123',
                'pp_ResponseCode': '000',
                'pp_TxnRefNo': 'TXN123'
            }
            
            # Calculate correct hash
            sorted_params = [str(response_data[key]) for key in sorted(response_data)]
            hash_string = 'test_salt' + '&' + '&'.join(sorted_params)
            correct_hash = hashlib.sha256(hash_string.encode()).hexdigest()
            response_data['pp_SecureHash'] = correct_hash
            
            # Test verification
            is_valid = verify_jazzcash_response(response_data)
            self.assertTrue(is_valid)

    def test_hash_verification_invalid(self):
        """Test hash verification with invalid data"""
        response_data = {
            'pp_Amount': '10000',
            'pp_BillReference': '123',
            'pp_ResponseCode': '000',
            'pp_SecureHash': 'invalid_hash'
        }
        
        is_valid = verify_jazzcash_response(response_data)
        self.assertFalse(is_valid)

    def test_amount_conversion(self):
        """Test PKR to paisa conversion"""
        with self.settings(
            JAZZCASH_MERCHANT_ID='test_merchant',
            JAZZCASH_PASSWORD='test_password',
            JAZZCASH_INTEGERITY_SALT='test_salt',
            JAZZCASH_RETURN_URL='http://test.com/callback/'
        ):
            test_cases = [
                (Decimal('1.00'), 100),
                (Decimal('99.99'), 9999),
                (Decimal('150.50'), 15050),
            ]
            
            for amount, expected_paisa in test_cases:
                params = get_jazzcash_payment_params(amount=amount, order_id=1)
                self.assertEqual(params['pp_Amount'], expected_paisa)