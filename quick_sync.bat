@echo off
echo 🔄 Quick GitHub Sync...

REM Clean up
if exist nul del nul

REM Configure git
git config core.autocrlf true

REM Add, commit, push
git add .
set /p msg="Enter commit message: "
if "%msg%"=="" set msg=Quick update
git commit -m "%msg%"
git push origin master

echo ✅ Done!
pause