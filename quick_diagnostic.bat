@echo off
echo 🔍 Quick Diagnostic Test...

echo Testing basic models only...
python manage.py test marketplace.tests.test_basic_models --settings=marketplace.test_settings --verbosity=1 > diagnostic_output.txt 2>&1

echo.
echo Results saved to diagnostic_output.txt
echo Opening results...
type diagnostic_output.txt

pause