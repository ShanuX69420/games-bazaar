@echo off
echo 🧹 Cleaning and uploading...

REM Remove cache files
git rm -r --cached . 2>nul
git add .

REM Commit with descriptive message
set /p msg="Enter what you changed: "
if "%msg%"=="" set msg="Code updates"

git commit -m "✨ %msg%"
git push

echo ✅ Clean upload done!
pause