@echo off
echo 🧪 Testing Utilities (Models + Utils)...

echo 📦 Testing Models...
python manage.py test marketplace.tests.test_models --settings=marketplace.test_settings --verbosity=2

echo.
echo 🔧 Testing Utilities...
python manage.py test marketplace.tests.test_utils --settings=marketplace.test_settings --verbosity=2

echo.
echo ✅ Utility tests completed!
pause