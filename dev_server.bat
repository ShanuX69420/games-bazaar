@echo off
echo 🚀 Starting Django Development Server...
echo.
echo 🔧 Using Development Settings (DEBUG=True)
echo 📡 Server will be available at: http://127.0.0.1:8000/
echo.
echo ⚡ Features enabled:
echo    - ✅ Debug mode ON
echo    - ✅ Hot reload enabled
echo    - ✅ Console logging
echo    - ✅ JazzCash sandbox mode
echo    - ✅ SQLite database
echo.
echo 🛑 Press Ctrl+C to stop the server
echo.
python manage.py runserver --settings=core.settings.development
pause