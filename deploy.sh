#!/bin/bash
# Production Deployment Script for Gamers Market

echo "🚀 Starting deployment process..."

# Save current commit for rollback
CURRENT_COMMIT=$(git rev-parse HEAD)
echo "📝 Current commit: $CURRENT_COMMIT" > .last_deploy_commit

# Git operations
echo "📋 Adding all changes to git..."
git add .

echo "💾 Committing changes..."
read -p "Enter commit message (or press Enter for default): " COMMIT_MSG
COMMIT_MSG=${COMMIT_MSG:-"Deploy $(date '+%Y-%m-%d %H:%M:%S')"}
git commit -m "$COMMIT_MSG"

echo "⬆️ Pushing to remote repository..."
git push origin $(git branch --show-current)

# Set environment
export DJANGO_SETTINGS_MODULE=core.settings.production

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Collect static files
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# Run migrations
echo "🗃️ Running database migrations..."
python manage.py migrate

# Run system checks
echo "🔍 Running system checks..."
python manage.py check --deploy

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

echo "✅ Deployment complete! Server running on port 8000"