#!/bin/bash
set -euo pipefail

# Container build script for YeetMouse RPM builder
# This script runs inside the Fedora container and handles:
# - Cloning YeetMouse source from GitHub
# - Creating source tarball for rpmbuild
# - Setting up rpmbuild directory structure
# - Building RPM packages using static spec files

# Configuration
YEETMOUSE_REPO="https://github.com/AndyFilter/YeetMouse.git"
BUILD_DIR="/build"
OUTPUT_DIR="/output"
SOURCE_DIR="${BUILD_DIR}/yeetmouse-source"
SPEC_DIR="/specs"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Cleanup function
cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log_error "Build failed with exit code $exit_code"
    fi
    return $exit_code
}

trap cleanup EXIT

# Verify output directory exists
if [ ! -d "$OUTPUT_DIR" ]; then
    log_error "Output directory does not exist: $OUTPUT_DIR"
    exit 1
fi

log_info "Starting YeetMouse build process"
log_info "Output directory: $OUTPUT_DIR"

# Clone YeetMouse repository
log_info "Cloning YeetMouse repository from GitHub..."
if [ -d "$SOURCE_DIR" ]; then
    log_warn "Source directory already exists, updating..."
    cd "$SOURCE_DIR"
    git fetch origin
    git reset --hard origin/HEAD
else
    mkdir -p "$BUILD_DIR"
    git clone "$YEETMOUSE_REPO" "$SOURCE_DIR"
fi

cd "$SOURCE_DIR"
log_info "YeetMouse repository ready at: $SOURCE_DIR"

# Extract version from Makefile DKMS_VER variable
YEETMOUSE_VERSION=$(grep "^DKMS_VER" "$SOURCE_DIR/Makefile" | cut -d'=' -f2 | xargs)
if [ -z "$YEETMOUSE_VERSION" ]; then
    log_warn "Could not extract version from Makefile, using default"
    YEETMOUSE_VERSION="0.9.2"
fi
log_info "YeetMouse version: $YEETMOUSE_VERSION"

# Get git commit hash for traceability
GIT_HASH=$(cd "$SOURCE_DIR" && git rev-parse --short HEAD)
log_info "Git commit: $GIT_HASH"

# Build release string with git hash and date: 1.git<hash>.<date>
RELEASE_DATE=$(date +%Y%m%d)
RELEASE_NUMBER="1.git${GIT_HASH}.${RELEASE_DATE}"
log_info "Release number: $RELEASE_NUMBER"

# Create source tarball for rpmbuild
log_info "Creating source tarball..."
cd "$BUILD_DIR"
# Create a clean copy without .git directory
TARBALL_DIR="yeetmouse"
rm -rf "$TARBALL_DIR"
cp -r "$SOURCE_DIR" "$TARBALL_DIR"
rm -rf "$TARBALL_DIR/.git"

# Create tarball
tar czf "yeetmouse-${YEETMOUSE_VERSION}.tar.gz" "$TARBALL_DIR"
log_info "Source tarball created: yeetmouse-${YEETMOUSE_VERSION}.tar.gz"

# Setup RPM build environment
log_info "Setting up RPM build environment..."
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Copy source tarball to SOURCES
cp "${BUILD_DIR}/yeetmouse-${YEETMOUSE_VERSION}.tar.gz" ~/rpmbuild/SOURCES/
log_info "Source tarball copied to rpmbuild/SOURCES"

# Verify spec files exist
if [ ! -d "$SPEC_DIR" ]; then
    log_error "Spec directory not found: $SPEC_DIR"
    exit 1
fi

# Copy spec files to SPECS directory
log_info "Copying spec files from $SPEC_DIR..."
cp "$SPEC_DIR/akmod-yeetmouse.spec" ~/rpmbuild/SPECS/
cp "$SPEC_DIR/kmod-yeetmouse.spec" ~/rpmbuild/SPECS/
cp "$SPEC_DIR/yeetmouse-gui.spec" ~/rpmbuild/SPECS/
log_info "Spec files copied to rpmbuild/SPECS"

# Also copy spec files to output for reference
cp "$SPEC_DIR"/*.spec "$OUTPUT_DIR/"
log_info "Spec files copied to output directory for reference"

# Build akmod RPM package
log_info "Building akmod RPM package..."
if ! rpmbuild -bb ~/rpmbuild/SPECS/akmod-yeetmouse.spec \
    --define "_topdir $HOME/rpmbuild" \
    --define "release_number ${RELEASE_NUMBER}" \
    2>&1 | tee "$OUTPUT_DIR/akmod-rpmbuild.log"; then
    log_error "Akmod RPM build failed, check akmod-rpmbuild.log for details"
    exit 1
fi

log_info "Akmod RPM package built successfully"
# Find and copy the RPM file
AKMOD_RPM=$(find ~/rpmbuild/RPMS -name "akmod-yeetmouse-*.rpm" -type f)
if [ -n "$AKMOD_RPM" ]; then
    cp "$AKMOD_RPM" "$OUTPUT_DIR/"
    log_info "Akmod RPM copied to output: $(basename "$AKMOD_RPM")"
else
    log_error "Akmod RPM file not found in rpmbuild directory"
    exit 1
fi

# Build kmod RPM package
log_info "Building kmod RPM package..."
if ! rpmbuild -bb ~/rpmbuild/SPECS/kmod-yeetmouse.spec \
    --define "_topdir $HOME/rpmbuild" \
    --define "release_number ${RELEASE_NUMBER}" \
    2>&1 | tee "$OUTPUT_DIR/kmod-rpmbuild.log"; then
    log_error "Kmod RPM build failed, check kmod-rpmbuild.log for details"
    exit 1
fi

log_info "Kmod RPM package built successfully"
# Find and copy the RPM file
KMOD_RPM=$(find ~/rpmbuild/RPMS -name "kmod-yeetmouse-*.rpm" -type f)
if [ -n "$KMOD_RPM" ]; then
    cp "$KMOD_RPM" "$OUTPUT_DIR/"
    log_info "Kmod RPM copied to output: $(basename "$KMOD_RPM")"
else
    log_error "Kmod RPM file not found in rpmbuild directory"
    exit 1
fi

# Build GUI RPM package
log_info "Building GUI RPM package..."
if ! rpmbuild -bb ~/rpmbuild/SPECS/yeetmouse-gui.spec \
    --define "_topdir $HOME/rpmbuild" \
    --define "release_number ${RELEASE_NUMBER}" \
    2>&1 | tee "$OUTPUT_DIR/gui-rpmbuild.log"; then
    log_error "GUI RPM build failed, check gui-rpmbuild.log for details"
    exit 1
fi

log_info "GUI RPM package built successfully"
# Find and copy the RPM file
GUI_RPM=$(find ~/rpmbuild/RPMS -name "yeetmouse-gui-*.rpm" -type f)
if [ -n "$GUI_RPM" ]; then
    cp "$GUI_RPM" "$OUTPUT_DIR/"
    log_info "GUI RPM copied to output: $(basename "$GUI_RPM")"
else
    log_error "GUI RPM file not found in rpmbuild directory"
    exit 1
fi

# Store build metadata
log_info "Storing build metadata..."
cat > "$OUTPUT_DIR/build-metadata.txt" <<EOF
Build Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
YeetMouse Version: $YEETMOUSE_VERSION
YeetMouse Git Hash: $GIT_HASH
YeetMouse Source: $YEETMOUSE_REPO
Build Directory: $SOURCE_DIR
Spec Files Used:
  - akmod-yeetmouse.spec (automatic kernel module)
  - kmod-yeetmouse.spec (kernel-specific module)
  - yeetmouse-gui.spec (GUI application)
RPM Packages Built:
  - akmod-yeetmouse-${YEETMOUSE_VERSION}-1.rpm
  - kmod-yeetmouse-${YEETMOUSE_VERSION}-1.rpm
  - yeetmouse-gui-${YEETMOUSE_VERSION}-1.rpm
EOF

log_info "Build metadata stored"

log_info "YeetMouse build completed successfully"
log_info "Output files available in: $OUTPUT_DIR"
