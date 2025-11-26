#!/bin/bash
set -euo pipefail

# Kernel Version Resolver Script
# Determines target kernel versions by inspecting distribution images
# Supports both Aurora (main kernel) and Bazzite (custom kernel)

# Default values
KERNEL_TYPE=""
EXPLICIT_VERSION=""

# Parse CLI options
while [[ $# -gt 0 ]]; do
  case $1 in
    --kernel-type)
      KERNEL_TYPE="$2"
      shift 2
      ;;
    --version)
      EXPLICIT_VERSION="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 --kernel-type <main|bazzite> [--version <version>]"
      exit 1
      ;;
  esac
done

# Validate kernel type
if [[ -z "$KERNEL_TYPE" ]]; then
  echo "Error: --kernel-type is required"
  echo "Usage: $0 --kernel-type <main|bazzite> [--version <version>]"
  exit 1
fi

if [[ "$KERNEL_TYPE" != "main" && "$KERNEL_TYPE" != "bazzite" ]]; then
  echo "Error: kernel-type must be 'main' or 'bazzite', got '$KERNEL_TYPE'"
  exit 1
fi

# If explicit version provided, validate and use it
if [[ -n "$EXPLICIT_VERSION" ]]; then
  # Validate version format: should be like 6.17.8-300.fc43.x86_64 or 6.17.7-ba14.fc43.x86_64
  if ! [[ "$EXPLICIT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9a-z]+\.fc[0-9]+\.[a-z0-9_]+$ ]]; then
    echo "Error: Invalid kernel version format: $EXPLICIT_VERSION"
    echo "Expected format: X.Y.Z-RELEASE.fcVERSION.ARCH (e.g., 6.17.8-300.fc43.x86_64 or 6.17.7-ba14.fc43.x86_64)"
    exit 1
  fi
  echo "$EXPLICIT_VERSION"
  exit 0
fi

# Determine image to inspect based on kernel type
if [[ "$KERNEL_TYPE" == "main" ]]; then
  IMAGE="ghcr.io/ublue-os/aurora:latest"
elif [[ "$KERNEL_TYPE" == "bazzite" ]]; then
  IMAGE="ghcr.io/ublue-os/bazzite:latest"
fi

# Inspect image and extract ostree.linux label
echo "Inspecting image: $IMAGE" >&2

# Use skopeo to inspect the image
if ! INSPECT_OUTPUT=$(skopeo inspect "docker://$IMAGE" 2>&1); then
  echo "Error: Failed to inspect image $IMAGE" >&2
  echo "Skopeo error: $INSPECT_OUTPUT" >&2
  echo "Make sure skopeo is installed and the image is accessible" >&2
  echo "Check image availability at: https://github.com/orgs/ublue-os/packages" >&2
  exit 1
fi

# Extract ostree.linux label from the inspection output
if ! KERNEL_VERSION=$(echo "$INSPECT_OUTPUT" | jq -r '.Labels."ostree.linux" // empty' 2>&1); then
  echo "Error: Failed to parse image inspection output" >&2
  echo "jq error: $KERNEL_VERSION" >&2
  echo "Ensure jq is installed" >&2
  exit 1
fi

# Validate that we got a kernel version
if [[ -z "$KERNEL_VERSION" ]]; then
  echo "Error: Could not find ostree.linux label in image $IMAGE"
  echo "Image labels:"
  echo "$INSPECT_OUTPUT" | jq '.Labels' 2>/dev/null || echo "Failed to display labels"
  exit 1
fi

# Validate kernel version format
if ! [[ "$KERNEL_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9a-z]+\.fc[0-9]+\.[a-z0-9_]+$ ]]; then
  echo "Error: Invalid kernel version format from image: $KERNEL_VERSION"
  echo "Expected format: X.Y.Z-RELEASE.fcVERSION.ARCH (e.g., 6.17.8-300.fc43.x86_64 or 6.17.7-ba14.fc43.x86_64)"
  exit 1
fi

# Output the kernel version
echo "$KERNEL_VERSION"
