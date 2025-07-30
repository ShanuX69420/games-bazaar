@echo off
echo ⏪ Rolling back GitHub repository...

REM Check if last sync commit file exists
if not exist ".last_sync_commit" (
    echo ❌ No previous sync found. Cannot rollback.
    echo 💡 Try: git log --oneline -5 (to see recent commits)
    pause
    exit /b 1
)

REM Get the last sync commit
for /f "tokens=3" %%i in ('findstr "Current commit:" .last_sync_commit') do set LAST_COMMIT=%%i

if "%LAST_COMMIT%"=="" (
    echo ❌ Invalid last commit data. Manual rollback needed.
    echo 💡 Use: git reset --hard ^<commit-hash^>
    pause
    exit /b 1
)

echo 📝 Last sync commit: %LAST_COMMIT%
for /f %%i in ('git rev-parse HEAD') do set CURRENT_COMMIT=%%i
echo 📝 Current commit: %CURRENT_COMMIT%

echo.
echo 📋 Changes that will be reverted:
git log --oneline %LAST_COMMIT%..HEAD

echo.
set /p confirm="⚠️ Are you sure you want to rollback? (y/N): "
if /i not "%confirm%"=="y" (
    echo ❌ Rollback cancelled.
    pause
    exit /b 0
)

REM Get current branch
for /f %%i in ('git branch --show-current') do set BRANCH=%%i

REM Perform rollback
echo ⏪ Resetting to previous commit...
git reset --hard %LAST_COMMIT%

echo ⬆️ Force pushing to GitHub...
git push origin %BRANCH% --force

echo ✅ Rollback complete!
echo 🌐 Branch: %BRANCH%
echo 📝 Reset to: %LAST_COMMIT%
pause