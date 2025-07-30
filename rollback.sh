#!/bin/bash
# Rollback Script for Gamers Market

echo "⏪ Starting rollback process..."

# Check if last deploy commit file exists
if [ ! -f ".last_deploy_commit" ]; then
    echo "❌ No previous deployment found. Cannot rollback."
    exit 1
fi

# Get the last deploy commit
LAST_COMMIT=$(cat .last_deploy_commit | grep "Current commit:" | cut -d' ' -f3)

if [ -z "$LAST_COMMIT" ]; then
    echo "❌ Invalid last commit data. Cannot rollback."
    exit 1
fi

echo "📝 Rolling back to commit: $LAST_COMMIT"

# Show what will be changed
echo "📋 Changes that will be reverted:"
git log --oneline $LAST_COMMIT..HEAD

read -p "Are you sure you want to rollback? (y/N): " confirm
if [[ $confirm != [yY] ]]; then
    echo "❌ Rollback cancelled."
    exit 0
fi

# Perform rollback
echo "⏪ Resetting to previous commit..."
git reset --hard $LAST_COMMIT

echo "⬆️ Force pushing to remote..."
git push origin $(git branch --show-current) --force

# Restart services
echo "🔄 Restarting application..."
export DJANGO_SETTINGS_MODULE=core.settings.production

# Install dependencies (in case they changed)
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Run migrations
echo "🗃️ Running database migrations..."
python manage.py migrate

# Restart gunicorn if running
echo "🔄 Restarting server..."
pkill -f gunicorn
sleep 2

# Start gunicorn server
echo "🌐 Starting production server..."
gunicorn core.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --worker-class gevent \
  --worker-connections 1000 \
  --max-requests 1000 \
  --timeout 30 \
  --keep-alive 5 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  --log-level info \
  --daemon

echo "✅ Rollback complete! Server running on port 8000"