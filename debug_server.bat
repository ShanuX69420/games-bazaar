@echo off
echo 🔍 Django Debug Server Startup...
echo.
echo 🚀 Starting server with maximum debugging...
echo.

REM First check if the settings work
echo 1️⃣ Checking Django configuration...
python manage.py check --settings=core.settings.development
if errorlevel 1 (
    echo ❌ Django configuration has errors!
    pause
    exit /b 1
)

echo ✅ Django configuration OK
echo.

REM Check if we can collect static files
echo 2️⃣ Checking static files...
python manage.py collectstatic --noinput --settings=core.settings.development --dry-run
if errorlevel 1 (
    echo ⚠️  Static files issue, but continuing...
)

echo.

REM Try to run migrations
echo 3️⃣ Applying any pending migrations...
python manage.py migrate --settings=core.settings.development

echo.
echo 4️⃣ Starting development server...
echo 📡 Server will be at: http://127.0.0.1:8000
echo 🔥 Debug mode: ON
echo 🛑 Press Ctrl+C to stop
echo.

REM Start server with verbose output
python manage.py runserver 127.0.0.1:8000 --settings=core.settings.development --verbosity=2

pause