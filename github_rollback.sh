#!/bin/bash
# Simple GitHub Rollback Script for Development

echo "⏪ Rolling back GitHub repository..."

# Check if last sync commit file exists
if [ ! -f ".last_sync_commit" ]; then
    echo "❌ No previous sync found. Cannot rollback."
    echo "💡 Try: git log --oneline -5 (to see recent commits)"
    exit 1
fi

# Get the last sync commit
LAST_COMMIT=$(cat .last_sync_commit | grep "Current commit:" | cut -d' ' -f3)

if [ -z "$LAST_COMMIT" ]; then
    echo "❌ Invalid last commit data. Manual rollback needed."
    echo "💡 Use: git reset --hard <commit-hash>"
    exit 1
fi

echo "📝 Last sync commit: $LAST_COMMIT"
echo "📋 Current commit: $(git rev-parse HEAD)"

# Show what will be reverted
echo ""
echo "📋 Changes that will be reverted:"
git log --oneline $LAST_COMMIT..HEAD

echo ""
read -p "⚠️ Are you sure you want to rollback? (y/N): " confirm
if [[ $confirm != [yY] ]]; then
    echo "❌ Rollback cancelled."
    exit 0
fi

# Get current branch
BRANCH=$(git branch --show-current)

# Perform rollback
echo "⏪ Resetting to previous commit..."
git reset --hard $LAST_COMMIT

echo "⬆️ Force pushing to GitHub..."
git push origin $BRANCH --force

echo "✅ Rollback complete!"
echo "🌐 Branch: $BRANCH"
echo "📝 Reset to: $LAST_COMMIT"