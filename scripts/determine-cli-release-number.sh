#!/bin/bash
set -euo pipefail

# CLI Release Number Determination Script
# Queries GitHub releases to determine the next CLI release number
# Implements increment logic: same version → increment, new version → 1

# Default values
YEETMOUSE_COMMIT=""
RELEASE_TYPE="stable"
GITHUB_REPO="abirkel/yeetmouse-rpm"

# Parse CLI options
while [[ $# -gt 0 ]]; do
  case $1 in
    --yeetmouse-commit)
      YEETMOUSE_COMMIT="$2"
      shift 2
      ;;
    --release-type)
      RELEASE_TYPE="$2"
      shift 2
      ;;
    --repo)
      GITHUB_REPO="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 --yeetmouse-commit <commit> [--release-type <stable|testing>] [--repo <owner/repo>]"
      exit 1
      ;;
  esac
done

# Validate required parameters
if [[ -z "$YEETMOUSE_COMMIT" ]]; then
  echo "Error: --yeetmouse-commit is required"
  exit 1
fi

if [[ "$RELEASE_TYPE" != "stable" && "$RELEASE_TYPE" != "testing" ]]; then
  echo "Error: release-type must be 'stable' or 'testing', got '$RELEASE_TYPE'"
  exit 1
fi

# Extract short commit (first 7 characters)
YEETMOUSE_SHORT_COMMIT="${YEETMOUSE_COMMIT:0:7}"

echo "Determining CLI release number for:" >&2
echo "  YeetMouse commit: $YEETMOUSE_COMMIT" >&2
echo "  YeetMouse short commit: $YEETMOUSE_SHORT_COMMIT" >&2
echo "  Release type: $RELEASE_TYPE" >&2
echo "  Repository: $GITHUB_REPO" >&2

# Query GitHub releases API
echo "Querying GitHub releases..." >&2

# Use gh CLI if available, otherwise fall back to curl
if command -v gh &> /dev/null; then
  if ! RELEASES_JSON=$(gh api "repos/${GITHUB_REPO}/releases" --paginate 2>&1); then
    echo "Error: Failed to query GitHub releases API using gh CLI" >&2
    echo "API response: $RELEASES_JSON" >&2
    echo "Check repository access and authentication" >&2
    exit 1
  fi
else
  # Fall back to curl with GitHub API
  if ! RELEASES_JSON=$(curl -fsSL "https://api.github.com/repos/${GITHUB_REPO}/releases?per_page=100" 2>&1); then
    echo "Error: Failed to query GitHub releases API" >&2
    echo "API response: $RELEASES_JSON" >&2
    echo "Install gh CLI for better API access: https://cli.github.com/" >&2
    exit 1
  fi
fi

# Check if we got any releases
if [[ -z "$RELEASES_JSON" ]] || [[ "$RELEASES_JSON" == "[]" ]]; then
  echo "No existing releases found, using release number 1" >&2
  echo "1"
  exit 0
fi

# Extract all asset names from releases
if ! ASSET_NAMES=$(echo "$RELEASES_JSON" | jq -r '.[].assets[].name' 2>&1); then
  echo "Error: Failed to parse releases JSON" >&2
  echo "jq error: $ASSET_NAMES" >&2
  echo "Ensure jq is installed and the API response is valid JSON" >&2
  exit 1
fi

if [[ -z "$ASSET_NAMES" ]]; then
  echo "No release assets found, using release number 1" >&2
  echo "1"
  exit 0
fi

# Look for CLI packages matching our commit
# Package naming pattern: yeetmouse-0-PKGREL.TIMESTAMPgSHORTCOMMIT.fc43.x86_64.rpm
# Example: yeetmouse-0-1.202512091624g99844bb.fc43.x86_64.rpm

echo "Searching for existing CLI packages..." >&2

# Escape dots in commit string for regex
YEETMOUSE_SHORT_COMMIT_ESCAPED="${YEETMOUSE_SHORT_COMMIT//./\\.}"

# Find matching packages and extract release numbers
# Pattern: yeetmouse-0-PKGREL.TIMESTAMPgSHORTCOMMIT.fc43.x86_64.rpm (not kmod-yeetmouse)
MATCHING_PACKAGES=$(echo "$ASSET_NAMES" | grep -E "^yeetmouse-0-[0-9]+\.[0-9]{12}g${YEETMOUSE_SHORT_COMMIT_ESCAPED}\.fc[0-9]+\.x86_64\.rpm$" || true)

# Further filter by release type by checking release names
if [[ -n "$MATCHING_PACKAGES" ]]; then
  # Get release names from the API response
  RELEASE_NAMES=$(echo "$RELEASES_JSON" | jq -r '.[].name' 2>&1)
  
  # Filter releases by type (e.g., v0.9.2-stable or v0.9.2-testing)
  FILTERED_RELEASES=$(echo "$RELEASE_NAMES" | grep -E "\-${RELEASE_TYPE}$" || true)
  
  if [[ -n "$FILTERED_RELEASES" ]]; then
    # Extract asset names from filtered releases only
    MATCHING_PACKAGES=$(echo "$RELEASES_JSON" | jq -r ".[] | select(.name | test(\"-${RELEASE_TYPE}$\")) | .assets[].name" | grep -E "^yeetmouse-0-[0-9]+\.[0-9]{12}g${YEETMOUSE_SHORT_COMMIT_ESCAPED}\.fc[0-9]+\.x86_64\.rpm$" || true)
  else
    MATCHING_PACKAGES=""
  fi
fi

if [[ -z "$MATCHING_PACKAGES" ]]; then
  echo "No matching CLI packages found for commit $YEETMOUSE_SHORT_COMMIT" >&2
  echo "Using release number 1" >&2
  echo "1"
  exit 0
fi

echo "Found matching CLI packages:" >&2
while IFS= read -r pkg; do
  echo "  $pkg" >&2
done <<< "$MATCHING_PACKAGES"

# Extract release numbers from matching packages
# Pattern: yeetmouse-0-PKGREL.TIMESTAMPgSHORTCOMMIT.fc43.x86_64.rpm
# We need to extract PKGREL (the number after -0- and before the timestamp)
RELEASE_NUMBERS=$(echo "$MATCHING_PACKAGES" | sed -E "s/^yeetmouse-0-([0-9]+)\.[0-9]{12}g${YEETMOUSE_SHORT_COMMIT_ESCAPED}\.fc[0-9]+\.x86_64\.rpm$/\1/")

# Find the highest release number
MAX_RELEASE=0
while IFS= read -r release; do
  if [[ -n "$release" ]] && [[ "$release" =~ ^[0-9]+$ ]]; then
    if [[ "$release" -gt "$MAX_RELEASE" ]]; then
      MAX_RELEASE="$release"
    fi
  fi
done <<< "$RELEASE_NUMBERS"

# Increment the release number
NEXT_RELEASE=$((MAX_RELEASE + 1))

echo "Highest existing CLI release: $MAX_RELEASE" >&2
echo "Next CLI release number: $NEXT_RELEASE" >&2

echo "$NEXT_RELEASE"
