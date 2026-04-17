#!/bin/bash
set -euo pipefail

# Kernel Package Fetcher Script
# Downloads kernel-devel packages for the target kernel version
# Supports both Fedora main kernel (from Koji) and OGC kernel (from GHCR OCI artifact)

# Default values
KERNEL_VERSION=""
KERNEL_TYPE=""
FEDORA_VERSION=""
OUTPUT_DIR="${PWD}"
MAX_RETRIES=2

# Parse CLI options
while [[ $# -gt 0 ]]; do
  case $1 in
    --kernel-version)
      KERNEL_VERSION="$2"
      shift 2
      ;;
    --kernel-type)
      KERNEL_TYPE="$2"
      shift 2
      ;;
    --fedora-version)
      FEDORA_VERSION="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 --kernel-version <version> --kernel-type <main|ogc> --fedora-version <version> [--output-dir <dir>]"
      exit 1
      ;;
  esac
done

# Validate required parameters
if [[ -z "$KERNEL_VERSION" ]]; then
  echo "Error: --kernel-version is required"
  exit 1
fi

if [[ -z "$KERNEL_TYPE" ]]; then
  echo "Error: --kernel-type is required"
  exit 1
fi

if [[ -z "$FEDORA_VERSION" ]]; then
  echo "Error: --fedora-version is required"
  exit 1
fi

if [[ "$KERNEL_TYPE" != "main" && "$KERNEL_TYPE" != "ogc" ]]; then
  echo "Error: kernel-type must be 'main' or 'ogc', got '$KERNEL_TYPE'"
  exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Function to download a file with retry logic
download_with_retry() {
  local url="$1"
  local output_file="$2"
  local retry_count=0

  while [[ $retry_count -lt $MAX_RETRIES ]]; do
    echo "Downloading: $url" >&2

    # Capture HTTP status code
    HTTP_CODE=$(curl -fLo "$output_file" -w "%{http_code}" "$url" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "200" ]]; then
      if [[ -s "$output_file" ]]; then
        echo "Successfully downloaded: $(basename "$output_file")" >&2
        return 0
      else
        echo "Warning: Downloaded file is empty, retrying..." >&2
        rm -f "$output_file"
      fi
    elif [[ "$HTTP_CODE" == "404" ]]; then
      echo "Error: Package not found (HTTP 404): $url" >&2
      echo "The kernel version may not be available in the repository" >&2
      rm -f "$output_file"
      return 1
    else
      echo "Warning: Download failed (HTTP $HTTP_CODE), retrying..." >&2
      rm -f "$output_file"
    fi
    retry_count=$((retry_count + 1))
  done

  echo "Error: Failed to download $url after $MAX_RETRIES attempts" >&2
  return 1
}

# Parse kernel version components
# Expected format: 6.17.8-300.fc43.x86_64 or 6.19.11-ogc1.1.fc43.x86_64
KERNEL_MAJOR_MINOR_PATCH=$(echo "$KERNEL_VERSION" | cut -d '-' -f 1)
KERNEL_RELEASE=$(echo "$KERNEL_VERSION" | cut -d '-' -f 2 | rev | cut -d '.' -f 2- | rev)
ARCH=$(echo "$KERNEL_VERSION" | rev | cut -d '.' -f 1 | rev)

echo "Parsed kernel version components:" >&2
echo "  Version: $KERNEL_MAJOR_MINOR_PATCH" >&2
echo "  Release: $KERNEL_RELEASE" >&2
echo "  Architecture: $ARCH" >&2

# Download packages based on kernel type
if [[ "$KERNEL_TYPE" == "main" ]]; then
  # Fedora main kernel from Koji
  BASE_URL="https://kojipkgs.fedoraproject.org/packages/kernel/${KERNEL_MAJOR_MINOR_PATCH}/${KERNEL_RELEASE}/${ARCH}"

  echo "Fetching main kernel packages from Koji:" >&2
  echo "  Base URL: $BASE_URL" >&2

  KERNEL_DEVEL_FILE="kernel-devel-${KERNEL_VERSION}.rpm"
  if ! download_with_retry "${BASE_URL}/${KERNEL_DEVEL_FILE}" "${OUTPUT_DIR}/${KERNEL_DEVEL_FILE}"; then
    echo "Error: Failed to download kernel-devel package" >&2
    echo "URL: ${BASE_URL}/${KERNEL_DEVEL_FILE}" >&2
    echo "Verify the kernel version exists at: https://kojipkgs.fedoraproject.org/packages/kernel/" >&2
    exit 1
  fi

  KERNEL_DEVEL_MATCHED_FILE="kernel-devel-matched-${KERNEL_VERSION}.rpm"
  if ! download_with_retry "${BASE_URL}/${KERNEL_DEVEL_MATCHED_FILE}" "${OUTPUT_DIR}/${KERNEL_DEVEL_MATCHED_FILE}"; then
    echo "Error: Failed to download kernel-devel-matched package" >&2
    echo "URL: ${BASE_URL}/${KERNEL_DEVEL_MATCHED_FILE}" >&2
    echo "Verify the kernel version exists at: https://kojipkgs.fedoraproject.org/packages/kernel/" >&2
    exit 1
  fi

elif [[ "$KERNEL_TYPE" == "ogc" ]]; then
  # OGC kernel from GHCR OCI artifact
  # ghcr.io/opengamingcollective/kernel-packages-fedora:latest-fc<N>
  OGC_IMAGE="ghcr.io/opengamingcollective/kernel-packages-fedora:latest-fc${FEDORA_VERSION}"

  echo "Fetching OGC kernel packages from GHCR OCI artifact:" >&2
  echo "  Image: $OGC_IMAGE" >&2

  TMPDIR=$(mktemp -d)
  trap 'rm -rf "$TMPDIR"' EXIT

  echo "Pulling OCI artifact (this downloads ~160MB)..." >&2
  if ! skopeo copy "docker://$OGC_IMAGE" "oci:${TMPDIR}/ogc:latest" 2>&1 | grep -v "^Copying" >&2; then
    echo "Error: Failed to pull OGC artifact $OGC_IMAGE" >&2
    echo "Check: https://github.com/orgs/OpenGamingCollective/packages" >&2
    exit 1
  fi

  MANIFEST_DIGEST=$(jq -r '.manifests[0].digest' "${TMPDIR}/ogc/index.json")
  MANIFEST_BLOB="${TMPDIR}/ogc/blobs/${MANIFEST_DIGEST/:///}"

  echo "Extracting kernel-devel packages from OCI layers..." >&2
  EXTRACTED=0

  while IFS= read -r line; do
    TITLE=$(echo "$line" | jq -r '.title')
    DIGEST=$(echo "$line" | jq -r '.digest')

    if [[ "$TITLE" =~ ^kernel-devel(-matched)?-[0-9] ]]; then
      BLOB_PATH="${TMPDIR}/ogc/blobs/${DIGEST/:///}"
      cp "$BLOB_PATH" "${OUTPUT_DIR}/${TITLE}"
      echo "Extracted: $TITLE" >&2
      EXTRACTED=$((EXTRACTED + 1))
    fi
  done < <(jq -c '.layers[] | {title: .annotations["org.opencontainers.image.title"], digest: .digest}' "$MANIFEST_BLOB")

  if [[ $EXTRACTED -eq 0 ]]; then
    echo "Error: No kernel-devel packages found in OGC artifact" >&2
    echo "Available layers:" >&2
    jq -r '.layers[].annotations["org.opencontainers.image.title"]' "$MANIFEST_BLOB" >&2 || true
    exit 1
  fi
fi

# Verify all packages exist and are non-empty
echo "Verifying downloaded packages:" >&2
PACKAGE_COUNT=0
for package in "${OUTPUT_DIR}"/kernel-devel*.rpm; do
  if [[ ! -f "$package" ]]; then
    echo "Error: Package file not found: $package" >&2
    exit 1
  fi
  if [[ ! -s "$package" ]]; then
    echo "Error: Package file is empty: $package" >&2
    exit 1
  fi
  PACKAGE_COUNT=$((PACKAGE_COUNT + 1))
  echo "  ✓ $(basename "$package") ($(stat -c%s "$package" 2>/dev/null) bytes)" >&2
done

if [[ $PACKAGE_COUNT -lt 2 ]]; then
  echo "Error: Expected at least 2 packages, found $PACKAGE_COUNT" >&2
  echo "Missing kernel-devel or kernel-devel-matched package" >&2
  exit 1
fi

echo "Successfully fetched all kernel packages ($PACKAGE_COUNT packages)" >&2
