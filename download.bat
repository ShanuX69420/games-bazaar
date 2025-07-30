@echo off
echo 📥 Downloading from GitHub...

git fetch
git reset --hard origin/master

echo ✅ Done!
pause