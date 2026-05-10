#!/bin/bash
# ---------------------------------------
# Git Commit + Auto Tagging Script
# Format: MAJOR.MINOR
# ---------------------------------------

VERSION_FILE=".version"   # Stores the last version
LOG_FILE=".git_release_log.txt"

# -------------------------------
# Check if inside a git repository
# -------------------------------
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Not a Git repository. Run this script inside a repo."
    exit 1
fi

# -------------------------------
# Parse arguments
# -------------------------------
BUMP_MAJOR=false
COMMIT_MSG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --major)
      BUMP_MAJOR=true
      shift
      ;;
    *)
      COMMIT_MSG="$1"
      shift
      ;;
  esac
done

if [ -z "$COMMIT_MSG" ]; then
    COMMIT_MSG="Auto commit"
    echo "✏️ No commit message provided. Using default: '$COMMIT_MSG'"
fi

# -------------------------------
# Commit all changes
# -------------------------------
git add .
git commit -m "$COMMIT_MSG"

# -------------------------------
# Push changes
# -------------------------------
BRANCH=$(git rev-parse --abbrev-ref HEAD)
git push origin "$BRANCH"
echo "✅ Changes pushed to branch $BRANCH."

# -------------------------------
# Determine current version
# -------------------------------
if [ ! -f "$VERSION_FILE" ]; then
    MAJOR=0
    MINOR=14
else
    LAST_VERSION=$(cat "$VERSION_FILE")
    IFS='.' read -r MAJOR MINOR <<< "$LAST_VERSION"
fi

# -------------------------------
# Increment version
# -------------------------------
if [ "$BUMP_MAJOR" = true ]; then
    MAJOR=$((MAJOR + 1))
    MINOR=0
    echo "🔼 Bumping major version!"
else
    MINOR=$((MINOR + 1))
fi

NEW_VERSION="$MAJOR.$MINOR"

# -------------------------------
# Create annotated tag
# -------------------------------
git tag -a "$NEW_VERSION" -m "Release $NEW_VERSION"
git push origin "$NEW_VERSION"
echo "🏷️ Tagged new release: $NEW_VERSION"

# Save new version
echo "$NEW_VERSION" > "$VERSION_FILE"

# -------------------------------
# Log the release locally
# -------------------------------
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")
echo "$TIMESTAMP - Commit: $COMMIT_MSG" >> "$LOG_FILE"
echo "$TIMESTAMP - Release Tag: $NEW_VERSION" >> "$LOG_FILE"

echo "✅ Done! New version: $NEW_VERSION"
