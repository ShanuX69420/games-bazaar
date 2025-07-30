@echo off
echo 🧪 Running Basic Model Tests...

echo 📦 Testing Basic Models (Game, Category, Profile, Transaction)...
python manage.py test marketplace.tests.test_basic_models --settings=marketplace.test_settings --verbosity=2

echo.
echo ✅ Basic tests completed!
pause