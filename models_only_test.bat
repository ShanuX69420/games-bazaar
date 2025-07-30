@echo off
echo 🧪 Testing Models Only (No URLs)...

echo 📦 Running Model Tests...
python manage.py test marketplace.tests.test_models --settings=marketplace.test_settings --verbosity=2

echo ✅ Model tests completed!
pause