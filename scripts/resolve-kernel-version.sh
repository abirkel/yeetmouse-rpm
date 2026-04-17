#!/bin/bash
set -euo pipefail

# Kernel Version Resolver Script
# Determines target kernel versions by inspecting distribution images
# Supports both Fedora main kernel (Aurora) and OGC kernel

# Default values
KERNEL_TYPE=""
EXPLICIT_VERSION=""
FEDORA_VERSION=""

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
    --fedora-version)
      FEDORA_VERSION="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 --kernel-type <main|ogc> [--version <version>] [--fedora-version <N>]"
      exit 1
      ;;
  esac
done

# Validate kernel type
if [[ -z "$KERNEL_TYPE" ]]; then
  echo "Error: --kernel-type is required"
  echo "Usage: $0 --kernel-type <main|ogc> [--version <version>] [--fedora-version <N>]"
  exit 1
fi

if [[ "$KERNEL_TYPE" != "main" && "$KERNEL_TYPE" != "ogc" ]]; then
  echo "Error: kernel-type must be 'main' or 'ogc', got '$KERNEL_TYPE'"
  exit 1
fi

# OGC requires --fedora-version when not using --version
if [[ "$KERNEL_TYPE" == "ogc" && -z "$EXPLICIT_VERSION" && -z "$FEDORA_VERSION" ]]; then
  echo "Error: --fedora-version is required for kernel-type 'ogc'"
  echo "Usage: $0 --kernel-type ogc --fedora-version <N> [--version <version>]"
  exit 1
fi

# If explicit version provided, validate and use it
if [[ -n "$EXPLICIT_VERSION" ]]; then
  # Validate version format: X.Y.Z-RELEASE.fcVERSION.ARCH
  # Release segment allows dots (e.g. ogc1.1) as well as plain numbers (e.g. 300)
  if ! [[ "$EXPLICIT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9a-z.]+\.fc[0-9]+\.[a-z0-9_]+$ ]]; then
    echo "Error: Invalid kernel version format: $EXPLICIT_VERSION"
    echo "Expected format: X.Y.Z-RELEASE.fcVERSION.ARCH"
    echo "  e.g. 6.17.8-300.fc43.x86_64 or 6.19.11-ogc1.1.fc43.x86_64"
    exit 1
  fi
  echo "$EXPLICIT_VERSION"
  exit 0
fi

# Resolve version based on kernel type
if [[ "$KERNEL_TYPE" == "main" ]]; then
  IMAGE="ghcr.io/ublue-os/aurora:latest"

  echo "Inspecting image: $IMAGE" >&2

  if ! INSPECT_OUTPUT=$(skopeo inspect "docker://$IMAGE" 2>&1); then
    echo "Error: Failed to inspect image $IMAGE" >&2
    echo "Skopeo error: $INSPECT_OUTPUT" >&2
    echo "Make sure skopeo is installed and the image is accessible" >&2
    exit 1
  fi

  if ! KERNEL_VERSION=$(echo "$INSPECT_OUTPUT" | jq -r '.Labels."ostree.linux" // empty' 2>&1); then
    echo "Error: Failed to parse image inspection output" >&2
    echo "jq error: $KERNEL_VERSION" >&2
    exit 1
  fi

  if [[ -z "$KERNEL_VERSION" ]]; then
    echo "Error: Could not find ostree.linux label in image $IMAGE" >&2
    echo "Image labels:" >&2
    echo "$INSPECT_OUTPUT" | jq '.Labels' 2>/dev/null >&2 || true
    exit 1
  fi

elif [[ "$KERNEL_TYPE" == "ogc" ]]; then
  OGC_IMAGE="ghcr.io/opengamingcollective/kernel-packages-fedora:latest-fc${FEDORA_VERSION}"

  echo "Pulling OGC artifact: $OGC_IMAGE" >&2

  TMPDIR=$(mktemp -d)
  trap 'rm -rf "$TMPDIR"' EXIT

  if ! skopeo copy "docker://$OGC_IMAGE" "oci:${TMPDIR}/ogc:latest" 2>&1 | grep -v "^Copying" >&2; then
    echo "Error: Failed to pull OGC artifact $OGC_IMAGE" >&2
    echo "Make sure skopeo is installed and the image is accessible" >&2
    echo "Check: https://github.com/orgs/OpenGamingCollective/packages" >&2
    exit 1
  fi

  MANIFEST_DIGEST=$(jq -r '.manifests[0].digest' "${TMPDIR}/ogc/index.json")
  MANIFEST_BLOB="${TMPDIR}/ogc/blobs/${MANIFEST_DIGEST/:///}"

  if ! KERNEL_VERSION=$(jq -r '
    .layers[].annotations["org.opencontainers.image.title"]
    | select(test("^kernel-devel-[0-9]"))
    | ltrimstr("kernel-devel-")
    | rtrimstr(".rpm")
  ' "$MANIFEST_BLOB" 2>&1); then
    echo "Error: Failed to parse OGC manifest" >&2
    echo "jq error: $KERNEL_VERSION" >&2
    exit 1
  fi

  if [[ -z "$KERNEL_VERSION" ]]; then
    echo "Error: Could not find kernel-devel layer in OGC manifest" >&2
    echo "Available layers:" >&2
    jq -r '.layers[].annotations["org.opencontainers.image.title"]' "$MANIFEST_BLOB" >&2 || true
    exit 1
  fi
fi

# Validate kernel version format
# Release segment allows dots (e.g. ogc1.1) as well as plain numbers (e.g. 300)
if ! [[ "$KERNEL_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9a-z.]+\.fc[0-9]+\.[a-z0-9_]+$ ]]; then
  echo "Error: Invalid kernel version format resolved: $KERNEL_VERSION" >&2
  echo "Expected format: X.Y.Z-RELEASE.fcVERSION.ARCH" >&2
  exit 1
fi

echo "$KERNEL_VERSION"
