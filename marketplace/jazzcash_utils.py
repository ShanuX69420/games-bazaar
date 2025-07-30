# experiment/marketplace/jazzcash_utils.py

import hashlib
from datetime import datetime, timedelta
from django.conf import settings

def get_jazzcash_payment_params(amount, order_id):
    pp_Amount = int(amount * 100)
    now = datetime.now()
    pp_TxnDateTime = now.strftime('%Y%m%d%H%M%S')
    pp_TxnExpiryDateTime = (now + timedelta(hours=1)).strftime('%Y%m%d%H%M%S')
    pp_TxnRefNo = 'TXN' + now.strftime('%Y%m%d%H%M%S')

    params = {
        'pp_Version': '1.1',
        'pp_TxnType': 'MWALLET',
        'pp_Language': 'EN',
        'pp_MerchantID': settings.JAZZCASH_MERCHANT_ID,
        'pp_Password': settings.JAZZCASH_PASSWORD,
        'pp_TxnRefNo': pp_TxnRefNo,
        'pp_Amount': pp_Amount,
        'pp_TxnCurrency': 'PKR',
        'pp_TxnDateTime': pp_TxnDateTime,
        'pp_TxnExpiryDateTime': pp_TxnExpiryDateTime,
        'pp_BillReference': str(order_id),
        'pp_Description': f'Payment for Order ID: {order_id}',
        'pp_ReturnURL': settings.JAZZCASH_RETURN_URL,
        'pp_SecureHash': '',
        'ppmpf_1': '1',
        'ppmpf_2': '2',
        'ppmpf_3': '3',
        'ppmpf_4': '4',
        'ppmpf_5': '5',
    }

    # Create a string for hashing by sorting dictionary values alphabetically by key
    sorted_params_list = [str(params[key]) for key in sorted(params) if key != 'pp_SecureHash' and params[key]]
    
    hash_string = settings.JAZZCASH_INTEGERITY_SALT + '&' + '&'.join(sorted_params_list)
    
    params['pp_SecureHash'] = hashlib.sha256(hash_string.encode()).hexdigest()

    return params

def verify_jazzcash_response(response_data):
    if 'pp_SecureHash' not in response_data:
        return False

    received_hash = response_data.get('pp_SecureHash', '')
    
    # Create a list of values for hashing, sorted alphabetically by key
    # Exclude pp_SecureHash from the hash calculation itself
    sorted_params_list = [str(response_data[key]) for key in sorted(response_data) if key != 'pp_SecureHash' and response_data[key]]

    # Prepend the Integrity Salt
    hash_string = settings.JAZZCASH_INTEGERITY_SALT + '&' + '&'.join(sorted_params_list)
    
    # Generate the hash
    generated_hash = hashlib.sha256(hash_string.encode()).hexdigest()

    # Compare the generated hash with the one received from Jazzcash
    return generated_hash.lower() == received_hash.lower()