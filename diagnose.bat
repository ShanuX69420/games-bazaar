@echo off
echo 🔍 Django Server Diagnostics
echo ============================
echo.

echo 1️⃣ Testing basic network connectivity...
python -c "import socket; s=socket.socket(); s.connect(('127.0.0.1', 80)); print('Network OK'); s.close()" 2>nul || echo "Network connectivity issue"

echo.
echo 2️⃣ Testing if Django can import...
python -c "import django; print('Django version:', django.get_version())"

echo.
echo 3️⃣ Testing Django settings...
python manage.py check --settings=core.settings.simple_dev

echo.
echo 4️⃣ Testing database connection...
python manage.py dbshell --settings=core.settings.simple_dev --command=".quit" 2>nul && echo "Database OK" || echo "Database issue"

echo.
echo 5️⃣ Testing static files...
python manage.py findstatic admin/css/base.css --settings=core.settings.simple_dev >nul 2>&1 && echo "Static files OK" || echo "Static files issue"

echo.
echo 6️⃣ Starting server with detailed output...
echo Press Ctrl+C to stop after testing
echo.
python manage.py runserver 127.0.0.1:8082 --settings=core.settings.simple_dev --verbosity=3

pause