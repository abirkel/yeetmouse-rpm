#!/bin/bash
set -euo pipefail

# Container build script for YeetMouse RPM builder
# This script runs inside the Fedora container and handles:
# - Cloning YeetMouse source from GitHub
# - Detecting kernel version
# - Compiling kernel module
# - Compiling GUI application

# Configuration
YEETMOUSE_REPO="https://github.com/AndyFilter/YeetMouse.git"
BUILD_DIR="/build"
OUTPUT_DIR="/output"
SOURCE_DIR="${BUILD_DIR}/yeetmouse-source"

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

# Detect kernel version
log_info "Detecting kernel version..."
KERNEL_VERSION=$(uname -r)
KERNEL_RELEASE=$(uname -r | cut -d'-' -f1)
log_info "Kernel version: $KERNEL_VERSION"
log_info "Kernel release: $KERNEL_RELEASE"

# Verify kernel headers are available
KERNEL_BUILD_DIR="/lib/modules/${KERNEL_VERSION}/build"
if [ ! -d "$KERNEL_BUILD_DIR" ]; then
    log_error "Kernel headers not found at: $KERNEL_BUILD_DIR"
    exit 1
fi
log_info "Kernel headers found at: $KERNEL_BUILD_DIR"

# Compile kernel module
log_info "Compiling YeetMouse kernel module..."
if [ ! -f "driver/Makefile" ]; then
    log_error "Driver Makefile not found at: driver/Makefile"
    exit 1
fi

cd "$SOURCE_DIR/driver"
log_info "Building kernel module in: $(pwd)"

# Build kernel module using kernel Makefile
make -C "$KERNEL_BUILD_DIR" M="$(pwd)" modules 2>&1 | tee "$OUTPUT_DIR/kernel-build.log"

# Verify kernel module was created
if [ ! -f "yeetmouse.ko" ]; then
    log_error "Kernel module compilation failed: yeetmouse.ko not found"
    exit 1
fi
log_info "Kernel module compiled successfully: yeetmouse.ko"

# Copy kernel module to output
cp yeetmouse.ko "$OUTPUT_DIR/"
log_info "Kernel module copied to output directory"

# Compile GUI application
log_info "Compiling YeetMouse GUI application..."
if [ ! -f "$SOURCE_DIR/gui/Makefile" ]; then
    log_warn "GUI Makefile not found at: gui/Makefile, skipping GUI compilation"
else
    cd "$SOURCE_DIR/gui"
    log_info "Building GUI in: $(pwd)"
    
    # Build GUI application
    make 2>&1 | tee "$OUTPUT_DIR/gui-build.log"
    
    # Check if GUI binary was created (name may vary)
    if [ -f "yeetmouse-gui" ]; then
        cp yeetmouse-gui "$OUTPUT_DIR/"
        log_info "GUI application compiled and copied to output directory"
    elif [ -f "yeetmouse" ]; then
        cp yeetmouse "$OUTPUT_DIR/"
        log_info "GUI application compiled and copied to output directory"
    else
        log_warn "GUI binary not found after compilation, continuing without GUI"
    fi
fi

# Generate akmod spec file
log_info "Generating akmod spec file..."

# Extract version from Makefile DKMS_VER variable
YEETMOUSE_VERSION=$(grep "^DKMS_VER" "$SOURCE_DIR/Makefile" | cut -d'=' -f2 | xargs)
if [ -z "$YEETMOUSE_VERSION" ]; then
    log_warn "Could not extract version from Makefile, using default"
    YEETMOUSE_VERSION="0.1.0"
fi

# Get git commit hash for traceability
GIT_HASH=$(cd "$SOURCE_DIR" && git rev-parse --short HEAD)

# Get current date for release number
RELEASE_DATE=$(date +%Y%m%d)

# Build release string: 1.git<hash>.<date>
RELEASE_NUMBER="1.git${GIT_HASH}.${RELEASE_DATE}"

# Create akmod spec file
AKMOD_SPEC="$OUTPUT_DIR/akmod-yeetmouse.spec"
cat > "$AKMOD_SPEC" <<'SPEC_EOF'
%define kernel_module_package_release 1

Name:           akmod-yeetmouse
Version:        %{YEETMOUSE_VERSION}
Release:        %{RELEASE_NUMBER}%{?dist}
Summary:        Kernel module for YeetMouse mouse acceleration
License:        GPL-2.0-or-later

URL:            https://github.com/AndyFilter/YeetMouse
Source0:        https://github.com/AndyFilter/YeetMouse/archive/refs/tags/v%{version}.tar.gz

BuildRequires:  kernel-devel
BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  akmods

Requires:       akmods
Requires:       kernel-devel

%description
YeetMouse is a kernel module that provides customizable mouse acceleration.
This package provides the akmod (automatic kernel module) version that
automatically rebuilds the module when the kernel is updated.

%prep
%setup -q -n yeetmouse-%{version}

%build
cd driver
make -C /lib/modules/$(uname -r)/build M=$(pwd) modules

%install
mkdir -p %{buildroot}/lib/modules/%{kernel_version}-%{kernel_release}/extra/yeetmouse
install -m 644 driver/yeetmouse.ko %{buildroot}/lib/modules/%{kernel_version}-%{kernel_release}/extra/yeetmouse/

%post
/usr/sbin/depmod -a %{kernel_version}-%{kernel_release}
/sbin/modprobe yeetmouse || true

%preun
/sbin/modprobe -r yeetmouse || true

%files
/lib/modules/%{kernel_version}-%{kernel_release}/extra/yeetmouse/yeetmouse.ko

%changelog
* %{RELEASE_DATE} YeetMouse Builder <builder@yeetmouse.local> - %{version}-%{RELEASE_NUMBER}
- Automated build from YeetMouse repository (git commit %{GIT_HASH})

SPEC_EOF

# Replace template variables in spec file
sed -i "s/%{YEETMOUSE_VERSION}/$YEETMOUSE_VERSION/g" "$AKMOD_SPEC"
sed -i "s/%{RELEASE_NUMBER}/$RELEASE_NUMBER/g" "$AKMOD_SPEC"
sed -i "s/%{GIT_HASH}/$GIT_HASH/g" "$AKMOD_SPEC"
sed -i "s/%{RELEASE_DATE}/$RELEASE_DATE/g" "$AKMOD_SPEC"

log_info "Akmod spec file generated: $AKMOD_SPEC"

# Generate kmod spec file
log_info "Generating kmod spec file..."

# Create kmod spec file
KMOD_SPEC="$OUTPUT_DIR/kmod-yeetmouse.spec"
cat > "$KMOD_SPEC" <<'SPEC_EOF'
Name:           kmod-yeetmouse
Version:        %{YEETMOUSE_VERSION}
Release:        %{RELEASE_NUMBER}%{?dist}
Summary:        Kernel module for YeetMouse mouse acceleration
License:        GPL-2.0-or-later

URL:            https://github.com/AndyFilter/YeetMouse
Source0:        https://github.com/AndyFilter/YeetMouse/archive/refs/tags/v%{version}.tar.gz

BuildRequires:  kernel-devel = %{KERNEL_VERSION}
BuildRequires:  gcc
BuildRequires:  make

Requires:       kernel = %{KERNEL_VERSION}

%description
YeetMouse is a kernel module that provides customizable mouse acceleration.
This package provides the kmod version built for a specific kernel version.
The module must be rebuilt when the kernel is updated.

%prep
%setup -q -n yeetmouse-%{version}

%build
cd driver
make -C /lib/modules/%{KERNEL_VERSION}/build M=$(pwd) modules

%install
mkdir -p %{buildroot}/lib/modules/%{KERNEL_VERSION}/extra/yeetmouse
install -m 644 driver/yeetmouse.ko %{buildroot}/lib/modules/%{KERNEL_VERSION}/extra/yeetmouse/

%post
/usr/sbin/depmod -a %{KERNEL_VERSION}
/sbin/modprobe yeetmouse || true

%preun
/sbin/modprobe -r yeetmouse || true

%files
/lib/modules/%{KERNEL_VERSION}/extra/yeetmouse/yeetmouse.ko

%changelog
* %{RELEASE_DATE} YeetMouse Builder <builder@yeetmouse.local> - %{version}-%{RELEASE_NUMBER}
- Automated build from YeetMouse repository (git commit %{GIT_HASH})
- Built for kernel %{KERNEL_VERSION}

SPEC_EOF

# Replace template variables in spec file
sed -i "s/%{YEETMOUSE_VERSION}/$YEETMOUSE_VERSION/g" "$KMOD_SPEC"
sed -i "s/%{RELEASE_NUMBER}/$RELEASE_NUMBER/g" "$KMOD_SPEC"
sed -i "s/%{GIT_HASH}/$GIT_HASH/g" "$KMOD_SPEC"
sed -i "s/%{RELEASE_DATE}/$RELEASE_DATE/g" "$KMOD_SPEC"
sed -i "s/%{KERNEL_VERSION}/$KERNEL_VERSION/g" "$KMOD_SPEC"

log_info "Kmod spec file generated: $KMOD_SPEC"

# Generate GUI spec file
log_info "Generating GUI spec file..."

# Create GUI spec file
GUI_SPEC="$OUTPUT_DIR/yeetmouse-gui.spec"
cat > "$GUI_SPEC" <<'SPEC_EOF'
Name:           yeetmouse-gui
Version:        %{YEETMOUSE_VERSION}
Release:        %{RELEASE_NUMBER}%{?dist}
Summary:        GUI application for YeetMouse mouse acceleration configuration
License:        GPL-2.0-or-later

URL:            https://github.com/AndyFilter/YeetMouse
Source0:        https://github.com/AndyFilter/YeetMouse/archive/refs/tags/v%{version}.tar.gz

BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  glfw-devel
BuildRequires:  mesa-libGL-devel

Requires:       glfw
Requires:       mesa-libGL

%description
YeetMouse GUI is a graphical configuration tool for the YeetMouse kernel module.
It provides an intuitive interface for configuring mouse acceleration parameters,
custom curves, and other settings.

%prep
%setup -q -n yeetmouse-%{version}

%build
cd gui
make

%install
mkdir -p %{buildroot}%{_bindir}
install -m 755 gui/YeetMouseGui %{buildroot}%{_bindir}/yeetmouse-gui

%files
%{_bindir}/yeetmouse-gui

%post
echo "YeetMouse GUI installed successfully"
echo "Run 'yeetmouse-gui' to configure YeetMouse settings"

%changelog
* %{RELEASE_DATE} YeetMouse Builder <builder@yeetmouse.local> - %{version}-%{RELEASE_NUMBER}
- Automated build from YeetMouse repository (git commit %{GIT_HASH})

SPEC_EOF

# Replace template variables in spec file
sed -i "s/%{YEETMOUSE_VERSION}/$YEETMOUSE_VERSION/g" "$GUI_SPEC"
sed -i "s/%{RELEASE_NUMBER}/$RELEASE_NUMBER/g" "$GUI_SPEC"
sed -i "s/%{GIT_HASH}/$GIT_HASH/g" "$GUI_SPEC"
sed -i "s/%{RELEASE_DATE}/$RELEASE_DATE/g" "$GUI_SPEC"

log_info "GUI spec file generated: $GUI_SPEC"

# Setup RPM build environment
log_info "Setting up RPM build environment..."
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Build akmod RPM package
log_info "Building akmod RPM package..."
if rpmbuild -bb "$AKMOD_SPEC" \
    --define "_topdir $HOME/rpmbuild" \
    --define "kernel_version $KERNEL_VERSION" \
    --define "kernel_release $KERNEL_RELEASE" \
    2>&1 | tee "$OUTPUT_DIR/akmod-rpmbuild.log"; then
    log_info "Akmod RPM package built successfully"
    # Find and copy the RPM file
    AKMOD_RPM=$(find ~/rpmbuild/RPMS -name "akmod-yeetmouse-*.rpm" -type f)
    if [ -n "$AKMOD_RPM" ]; then
        cp "$AKMOD_RPM" "$OUTPUT_DIR/"
        log_info "Akmod RPM copied to output: $(basename "$AKMOD_RPM")"
    else
        log_warn "Akmod RPM file not found in rpmbuild directory"
    fi
else
    log_error "Akmod RPM build failed, check akmod-rpmbuild.log for details"
fi

# Build kmod RPM package
log_info "Building kmod RPM package..."
if rpmbuild -bb "$KMOD_SPEC" \
    --define "_topdir $HOME/rpmbuild" \
    2>&1 | tee "$OUTPUT_DIR/kmod-rpmbuild.log"; then
    log_info "Kmod RPM package built successfully"
    # Find and copy the RPM file
    KMOD_RPM=$(find ~/rpmbuild/RPMS -name "kmod-yeetmouse-*.rpm" -type f)
    if [ -n "$KMOD_RPM" ]; then
        cp "$KMOD_RPM" "$OUTPUT_DIR/"
        log_info "Kmod RPM copied to output: $(basename "$KMOD_RPM")"
    else
        log_warn "Kmod RPM file not found in rpmbuild directory"
    fi
else
    log_error "Kmod RPM build failed, check kmod-rpmbuild.log for details"
fi

# Build GUI RPM package
log_info "Building GUI RPM package..."
if rpmbuild -bb "$GUI_SPEC" \
    --define "_topdir $HOME/rpmbuild" \
    2>&1 | tee "$OUTPUT_DIR/gui-rpmbuild.log"; then
    log_info "GUI RPM package built successfully"
    # Find and copy the RPM file
    GUI_RPM=$(find ~/rpmbuild/RPMS -name "yeetmouse-gui-*.rpm" -type f)
    if [ -n "$GUI_RPM" ]; then
        cp "$GUI_RPM" "$OUTPUT_DIR/"
        log_info "GUI RPM copied to output: $(basename "$GUI_RPM")"
    else
        log_warn "GUI RPM file not found in rpmbuild directory"
    fi
else
    log_error "GUI RPM build failed, check gui-rpmbuild.log for details"
fi

# Copy spec files to output directory for persistence
log_info "Copying spec files to output directory..."
cp "$AKMOD_SPEC" "$OUTPUT_DIR/"
cp "$KMOD_SPEC" "$OUTPUT_DIR/"
cp "$GUI_SPEC" "$OUTPUT_DIR/"
log_info "Spec files copied to output directory"

# Store build metadata
log_info "Storing build metadata..."
cat > "$OUTPUT_DIR/build-metadata.txt" <<EOF
Build Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
Kernel Version: $KERNEL_VERSION
Kernel Release: $KERNEL_RELEASE
YeetMouse Version: $YEETMOUSE_VERSION
YeetMouse Git Hash: $GIT_HASH
YeetMouse Release: $RELEASE_NUMBER
YeetMouse Source: $YEETMOUSE_REPO
Build Directory: $SOURCE_DIR
Spec Files Generated:
  - akmod-yeetmouse.spec (automatic kernel module)
  - kmod-yeetmouse.spec (kernel-specific module)
  - yeetmouse-gui.spec (GUI application)
RPM Packages Built:
  - akmod-yeetmouse-${YEETMOUSE_VERSION}-${RELEASE_NUMBER}.rpm
  - kmod-yeetmouse-${YEETMOUSE_VERSION}-${RELEASE_NUMBER}.rpm
  - yeetmouse-gui-${YEETMOUSE_VERSION}-${RELEASE_NUMBER}.rpm
EOF

log_info "Build metadata stored"

log_info "YeetMouse build completed successfully"
log_info "Output files available in: $OUTPUT_DIR"
