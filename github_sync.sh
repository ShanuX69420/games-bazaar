#!/bin/bash
# Simple GitHub Sync Script for Development

echo "🔄 Syncing project to GitHub..."

# Save current commit for rollback
CURRENT_COMMIT=$(git rev-parse HEAD)
echo "📝 Current commit: $CURRENT_COMMIT" > .last_sync_commit

# Check git status
echo "📋 Current status:"
git status --short

# Add all changes
echo "➕ Adding all changes..."
git add .

# Check if there are changes to commit
if git diff --cached --quiet; then
    echo "ℹ️ No changes to commit."
    exit 0
fi

# Get commit message
read -p "💬 Enter commit message (or press Enter for default): " COMMIT_MSG
COMMIT_MSG=${COMMIT_MSG:-"Update project $(date '+%Y-%m-%d %H:%M:%S')"}

# Commit changes
echo "💾 Committing changes..."
git commit -m "$COMMIT_MSG"

# Push to GitHub
echo "⬆️ Pushing to GitHub..."
BRANCH=$(git branch --show-current)
git push origin $BRANCH

echo "✅ Successfully synced to GitHub!"
echo "🌐 Branch: $BRANCH"
echo "📝 Commit: $COMMIT_MSG"