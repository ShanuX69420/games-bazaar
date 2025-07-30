@echo off
echo 🎯 Running Specific Tests...

REM Using --settings flag instead

if "%1"=="" (
    echo Usage: test_specific.bat [test_type]
    echo.
    echo Available test types:
    echo   models        - Test models only (18 tests)
    echo   views         - Test views (simple) (5 tests)
    echo   jazzcash      - Test payment functionality (9 tests)
    echo   comprehensive - Test comprehensive suite (123 tests)
    echo   all           - Run all working tests (137 tests)
    pause
    exit /b 1
)

if "%1"=="models" (
    echo 📦 Testing Models...
    python manage.py test marketplace.tests.test_models --settings=marketplace.test_settings --verbosity=2
)

if "%1"=="views" (
    echo 🌐 Testing Views (Simple)...
    python manage.py test marketplace.tests.test_views_simple --settings=marketplace.test_settings --verbosity=2
)

if "%1"=="jazzcash" (
    echo 💳 Testing JazzCash...
    python manage.py test marketplace.tests.test_jazzcash --settings=marketplace.test_settings --verbosity=2
)

if "%1"=="comprehensive" (
    echo 🏆 Testing Comprehensive Suite...
    python manage.py test marketplace.tests.test_basic_models marketplace.tests.test_complete_models marketplace.tests.test_business_logic marketplace.tests.test_workflows marketplace.tests.test_payment_system marketplace.tests.test_security_validation --settings=marketplace.test_settings --verbosity=1
)

if "%1"=="all" (
    echo 🧪 Testing All Working Tests...
    python manage.py test marketplace.tests.test_basic_models marketplace.tests.test_complete_models marketplace.tests.test_business_logic marketplace.tests.test_workflows marketplace.tests.test_payment_system marketplace.tests.test_security_validation marketplace.tests.test_utils marketplace.tests.test_models marketplace.tests.test_views_simple marketplace.tests.test_jazzcash --settings=marketplace.test_settings --verbosity=1
)

echo ✅ Specific tests completed!
pause