# Security Tests

This folder contains automated security tests for the Django marketplace application.

## Files

- `security/simple_security_test.py` - Comprehensive security audit test script

## Running Security Tests

### Prerequisites
1. Start Django development server:
   ```bash
   python manage.py runserver
   ```

### Run Tests
```bash
# From project root directory
python tests/security/simple_security_test.py
```

## What Gets Tested

- ✅ CSRF Protection
- ✅ Rate Limiting 
- ✅ XSS Protection
- ✅ Security Headers
- ✅ File Structure
- ✅ Server Stability

## Expected Results

All tests should pass with 100% success rate. If any test fails, review the security middleware and settings configuration.

## Additional Manual Tests

For password security validation:
```bash
python manage.py shell
>>> from django.contrib.auth.password_validation import validate_password
>>> validate_password('weak123')  # Should raise ValidationError
```