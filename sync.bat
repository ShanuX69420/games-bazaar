@echo off
echo 🔄 Syncing project to GitHub...

REM Clean up problematic files
if exist nul del nul

REM Save current commit for rollback
for /f %%i in ('git rev-parse HEAD') do set CURRENT_COMMIT=%%i
echo 📝 Current commit: %CURRENT_COMMIT% > .last_sync_commit

REM Configure git for Windows line endings
git config core.autocrlf true

REM Check git status
echo 📋 Current status:
git status --short

REM Add all changes except problematic files
echo ➕ Adding all changes...
git add .
git reset HEAD nul 2>nul

REM Check if there are changes to commit
git diff --cached --quiet
if %errorlevel% equ 0 (
    echo ℹ️ No changes to commit.
    pause
    exit /b 0
)

REM Get commit message
set /p COMMIT_MSG="💬 Enter commit message (or press Enter for default): "
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Update project %date% %time%

REM Commit changes
echo 💾 Committing changes...
git commit -m "%COMMIT_MSG%"

REM Push to GitHub
echo ⬆️ Pushing to GitHub...
for /f %%i in ('git branch --show-current') do set BRANCH=%%i
git push origin %BRANCH%

echo ✅ Successfully synced to GitHub!
echo 🌐 Branch: %BRANCH%
echo 📝 Commit: %COMMIT_MSG%
pause