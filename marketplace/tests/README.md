# Comprehensive Test Suite for GamesBazaar

## Overview
This test suite was created to replace outdated tests and matches the current secure codebase after comprehensive manual security testing.

## Test Structure

### 🔒 Security Tests (`test_security.py`)
- **XSS Prevention**: Tests chat message sanitization and template filtering
- **File Upload Security**: Tests dangerous filename rejection, file size limits, fake image detection
- **UUID Security**: Tests order enumeration prevention and UUID-based URLs
- **Authorization**: Tests access control and IDOR prevention

### 🛒 Product Management Tests (`test_product_management.py`)
- **Product CRUD**: Create, edit, delete products with proper validation
- **Stock Management**: Stock updates, out-of-stock handling, authorization
- **Image Uploads**: Product images with security validation
- **Search & Filtering**: Product search functionality

### 👤 Authentication Tests (`test_authentication.py`)
- **Registration**: User signup with validation
- **Login/Logout**: Session management and authentication
- **Password Reset**: Reset functionality and token validation
- **Profiles**: User profile creation and management
- **Session Security**: Login requirements and session handling

### 💬 Messaging Tests (`test_messaging.py`)
- **Chat Functionality**: Message sending, conversation creation
- **Security**: XSS prevention in messages, authorization
- **Blocking System**: User blocking/unblocking
- **Rate Limiting**: Message spam prevention
- **File Attachments**: Image sharing in chat

## Running Tests

### Run All Tests
```bash
python manage.py test tests
```

### Run Specific Test Categories
```bash
# Security tests only
python manage.py test tests.test_security

# Product management tests only  
python manage.py test tests.test_product_management

# Authentication tests only
python manage.py test tests.test_authentication

# Messaging tests only
python manage.py test tests.test_messaging
```

### Run with Verbose Output
```bash
python manage.py test tests --verbosity=2
```

### Run Specific Test Methods
```bash
python manage.py test tests.test_security.XSSSecurityTest.test_xss_prevention_in_chat_messages
```

## Test Coverage

### Security Features Tested ✅
- XSS prevention in chat messages
- File upload validation (dangerous filenames, size limits, fake images)
- UUID-based order enumeration prevention
- Access control and authorization
- Rate limiting

### Core Features Tested ✅
- Product creation, editing, deletion
- Stock management
- User registration, login, logout
- Password reset functionality
- Chat messaging system
- User blocking system
- Image uploads (products and chat)

### Features Requiring Manual Testing ⚠️
- OAuth social login (Google, Facebook) - Test on production
- Email functionality - Test on production with real SMTP
- Payment processing - Test on production/staging
- Real-time WebSocket connections - Best tested manually
- Cross-browser compatibility
- Mobile responsiveness

## Test Database

Tests use Django's test database which is created and destroyed automatically. No special setup required.

## Debugging Tests

### View Test Output
```bash
python manage.py test tests --verbosity=2 --debug-mode
```

### Run Single Test with Debug
```bash
python manage.py test tests.test_security.XSSSecurityTest.test_xss_prevention_in_chat_messages --verbosity=2
```

## Maintenance

### When to Update Tests
- After adding new security features
- After changing authentication logic
- After modifying product management
- After updating messaging system
- After security vulnerabilities are fixed

### Adding New Tests
1. Follow the existing pattern in each test file
2. Use descriptive test method names
3. Include proper setup and teardown
4. Test both positive and negative scenarios
5. Document any complex test logic

## Integration with CI/CD

These tests are designed to run in continuous integration. Add to your CI pipeline:

```yaml
# Example GitHub Actions
- name: Run Tests
  run: |
    python manage.py test tests --verbosity=2
```

## Notes

- Tests are based on comprehensive manual security testing conducted
- All major security vulnerabilities found manually are now covered by automated tests  
- Tests use Django's built-in TestCase for database transactions
- File upload tests use SimpleUploadedFile for safe testing
- Authentication tests work with django-allauth
- Rate limiting tests may need adjustment based on your cache configuration