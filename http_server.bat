@echo off
echo 🌐 HTTP-Only Django Server
echo.
echo 🔧 Using Django built-in server (no WebSockets)
echo 📡 Server: http://127.0.0.1:8080
echo 🔄 Auto-reload: ON
echo.
echo 💡 Open your browser to: http://127.0.0.1:8080
echo.
python manage.py runserver 127.0.0.1:8080 --settings=core.settings.simple_dev
pause