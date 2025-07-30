@echo off
echo 🚀 Simple Django Server (Port 8080)
echo.
echo 🔧 Using basic HTTP server (not ASGI)
echo 📡 Open: http://127.0.0.1:8080
echo.
python manage.py runserver 127.0.0.1:8080 --settings=core.settings.development --noreload
pause