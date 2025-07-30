@echo off
echo 🔄 Restoring deleted files from GitHub...

REM First, fetch latest from GitHub
echo 📥 Fetching latest from GitHub...
git fetch origin master

REM Reset to match GitHub exactly
echo ⏪ Resetting to match GitHub repo...
git reset --hard origin/master

REM Check if any files are still missing
echo 📋 Checking status...
git status

echo ✅ All files restored from GitHub!
echo 💡 Your local files now match GitHub exactly
pause