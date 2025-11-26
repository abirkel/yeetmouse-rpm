#!/bin/bash
set -euo pipefail

CLEAN_WORKFLOWS=false

# Parse CLI options
while [[ $# -gt 0 ]]; do
  case $1 in
    --clean-workflows)
      CLEAN_WORKFLOWS=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--clean-workflows]"
      exit 1
      ;;
  esac
done

echo "Starting cleanup..."

# Remove all releases and their associated tags
echo "Removing all releases and their tags..."
RELEASES=$(gh release list --json tagName --jq '.[].tagName')
if [ -n "$RELEASES" ]; then
  while IFS= read -r tag; do
    echo "Deleting release and tag: $tag"
    gh release delete "$tag" --yes || true
    git tag -d "$tag" 2>/dev/null || true
    git push origin ":$tag" 2>/dev/null || true
  done <<< "$RELEASES"
else
  echo "No releases found"
fi

# Empty gh-pages repo
echo "Cleaning gh-pages repo..."
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

git clone --depth=1 --branch=gh-pages https://github.com/abirkel/yeetmouse-rpm.git "$TEMP_DIR/gh-pages"
cd "$TEMP_DIR/gh-pages"
git rm -r . 2>/dev/null || true
git commit -m "chore: clean gh-pages repo" || echo "Nothing to commit in gh-pages"
git push
cd - > /dev/null

# Remove .external_versions file
echo "Removing .external_versions file..."
if [ -f .external_versions ]; then
  git rm .external_versions
  git commit -m "chore: remove .external_versions"
else
  echo ".external_versions not found"
fi

# Delete all workflow runs (optional)
if [ "$CLEAN_WORKFLOWS" = true ]; then
  echo "Deleting all workflow runs..."
  REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
  RUNS=$(gh api "repos/$REPO/actions/runs" --jq '.workflow_runs[].id')
  if [ -n "$RUNS" ]; then
    while IFS= read -r run_id; do
      echo "Deleting workflow run: $run_id"
      gh api -X DELETE "repos/$REPO/actions/runs/$run_id" || true
    done <<< "$RUNS"
  else
    echo "No workflow runs found"
  fi
else
  echo "Skipping workflow run deletion (use --clean-workflows to enable)"
fi

# Final push
echo "Pushing all changes..."
git push

echo "Cleanup complete!"
