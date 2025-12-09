#!/bin/bash
set -euo pipefail

# Get Commit Timestamp Script
# Fetches the commit timestamp from GitHub in YYYYMMDDHHMM format

# Default values
COMMIT=""
GITHUB_REPO="AndyFilter/YeetMouse"

# Parse CLI options
while [[ $# -gt 0 ]]; do
  case $1 in
    --commit)
      COMMIT="$2"
      shift 2
      ;;
    --repo)
      GITHUB_REPO="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 --commit <commit_hash> [--repo <owner/repo>]" >&2
      exit 1
      ;;
  esac
done

# Validate required parameters
if [[ -z "$COMMIT" ]]; then
  echo "Error: --commit is required" >&2
  exit 1
fi

echo "Fetching commit timestamp for:" >&2
echo "  Repository: $GITHUB_REPO" >&2
echo "  Commit: $COMMIT" >&2

# Use gh CLI if available, otherwise fall back to curl
if command -v gh &> /dev/null; then
  if ! COMMIT_JSON=$(gh api "repos/${GITHUB_REPO}/commits/${COMMIT}" 2>&1); then
    echo "Error: Failed to fetch commit from GitHub API using gh CLI" >&2
    echo "API response: $COMMIT_JSON" >&2
    exit 1
  fi
else
  # Fall back to curl with GitHub API
  if ! COMMIT_JSON=$(curl -fsSL "https://api.github.com/repos/${GITHUB_REPO}/commits/${COMMIT}" 2>&1); then
    echo "Error: Failed to fetch commit from GitHub API" >&2
    echo "API response: $COMMIT_JSON" >&2
    echo "Install gh CLI for better API access: https://cli.github.com/" >&2
    exit 1
  fi
fi

# Extract commit date from JSON
if ! COMMIT_DATE=$(echo "$COMMIT_JSON" | jq -r '.commit.committer.date' 2>&1); then
  echo "Error: Failed to parse commit JSON" >&2
  echo "jq error: $COMMIT_DATE" >&2
  exit 1
fi

if [[ -z "$COMMIT_DATE" ]] || [[ "$COMMIT_DATE" == "null" ]]; then
  echo "Error: Could not extract commit date from API response" >&2
  exit 1
fi

# Convert ISO 8601 date to YYYYMMDDHHMM format
# Input format: 2024-12-09T16:24:35Z
# Output format: 202412091624
if ! TIMESTAMP=$(date -u -d "$COMMIT_DATE" '+%Y%m%d%H%M' 2>&1); then
  echo "Error: Failed to convert date format" >&2
  echo "Date conversion error: $TIMESTAMP" >&2
  echo "Commit date: $COMMIT_DATE" >&2
  exit 1
fi

echo "Commit timestamp: $TIMESTAMP" >&2
echo "$TIMESTAMP"
