@echo off
echo 📤 Uploading to GitHub...

git add .
git commit -m "Update"
git push

echo ✅ Done!
pause