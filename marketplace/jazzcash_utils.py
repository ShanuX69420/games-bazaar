# experiment/marketplace/jazzcash_utils.py

import hashlib
from datetime import datetime, timedelta
from django.conf import settings
from django.utils.html import escape

def get_jazzcash_payment_params(amount, order_id):
    pp_Amount = int(amount * 100)
    now = datetime.now()
    pp_TxnDateTime = now.strftime('%Y%m%d%H%M%S')
    pp_TxnExpiryDateTime = (now + timedelta(hours=1)).strftime('%Y%m%d%H%M%S')
    pp_TxnRefNo = 'TXN' + now.strftime('%Y%m%d%H%M%S') + str(order_id).zfill(4)

    # Build params without sensitive data first
    params = {
        'pp_Version': '1.1',
        'pp_TxnType': 'MWALLET',
        'pp_Language': 'EN',
        'pp_MerchantID': settings.JAZZCASH_MERCHANT_ID,
        'pp_TxnRefNo': pp_TxnRefNo,
        'pp_Amount': pp_Amount,
        'pp_TxnCurrency': 'PKR',
        'pp_TxnDateTime': pp_TxnDateTime,
        'pp_TxnExpiryDateTime': pp_TxnExpiryDateTime,
        'pp_BillReference': str(order_id),
        'pp_Description': f'Payment for Order ID: {escape(str(order_id))}',
        'pp_ReturnURL': settings.JAZZCASH_RETURN_URL,
        'ppmpf_1': '1',
        'ppmpf_2': '2',
        'ppmpf_3': '3',
        'ppmpf_4': '4',
        'ppmpf_5': '5',
    }

    # Create hash params with password (kept separate to avoid logging)
    hash_params = params.copy()
    hash_params['pp_Password'] = settings.JAZZCASH_PASSWORD
    
    # Create a string for hashing by sorting dictionary values alphabetically by key
    sorted_params_list = [str(hash_params[key]) for key in sorted(hash_params) if hash_params[key]]
    
    hash_string = settings.JAZZCASH_INTEGERITY_SALT + '&' + '&'.join(sorted_params_list)
    
    # Only add password to final params after hash calculation
    params['pp_Password'] = settings.JAZZCASH_PASSWORD
    params['pp_SecureHash'] = hashlib.sha256(hash_string.encode()).hexdigest()

    return params

def verify_jazzcash_response(response_data):
    if 'pp_SecureHash' not in response_data:
        return False

    received_hash = response_data.get('pp_SecureHash', '')
    
    # Try excluding empty parameters from hash calculation
    sorted_params_list = []
    for key in sorted(response_data.keys()):
        if key != 'pp_SecureHash' and response_data[key]:  # Only include non-empty values
            sorted_params_list.append(str(response_data[key]))

    # Prepend the Integrity Salt
    hash_string = settings.JAZZCASH_INTEGERITY_SALT + '&' + '&'.join(sorted_params_list)
    
    # Generate the hash
    generated_hash = hashlib.sha256(hash_string.encode()).hexdigest()


    # Compare the generated hash with the one received from Jazzcash
    return generated_hash.lower() == received_hash.lower()