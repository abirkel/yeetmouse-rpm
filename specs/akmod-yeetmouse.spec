%global debug_package %{nil}

Name:           akmod-yeetmouse
Version:        0.9.2
Release:        %{?release_number}%{!?release_number:1}%{?dist}
Summary:        Automatic kernel module for YeetMouse mouse acceleration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        yeetmouse-%{version}.tar.gz

BuildRequires:  kernel-devel
BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  akmods

Requires:       akmods
Requires:       kernel-devel

# Disable debug package generation for kernel modules
%global debug_package %{nil}

%description
YeetMouse is a kernel module that provides customizable mouse acceleration.
This package provides the akmod (automatic kernel module) version that
automatically rebuilds the module when the kernel is updated.

%prep
%setup -q -n yeetmouse

%build
# Copy sample config if config.h doesn't exist
if [ ! -f driver/config.h ]; then
    cp driver/config.sample.h driver/config.h
fi

# Find installed kernel-devel version
KVER=$(rpm -q kernel-devel --qf '%%{VERSION}-%%{RELEASE}.%%{ARCH}\n' | head -1)

# Build kernel module
cd driver
make -C /usr/src/kernels/${KVER} M=$(pwd) modules

%install
# Get kernel version from installed kernel-devel
KVER=$(rpm -q kernel-devel --qf '%%{VERSION}-%%{RELEASE}.%%{ARCH}\n' | head -1)

# Install kernel module
mkdir -p %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver
mkdir -p %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/FixedMath

# Copy source files for akmod rebuilds
cp -r driver/*.c %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/
cp -r driver/*.h %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/
cp -r driver/FixedMath/*.h %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/FixedMath/
cp driver/Makefile %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/
cp shared_definitions.h %{buildroot}/usr/src/akmods/yeetmouse-%{version}/
cp Makefile %{buildroot}/usr/src/akmods/yeetmouse-%{version}/

# Create akmod configuration
mkdir -p %{buildroot}/etc/akmods
cat > %{buildroot}/etc/akmods/yeetmouse.conf <<EOF
# YeetMouse akmod configuration
MODULE_NAME=yeetmouse
MODULE_VERSION=%{version}
MODULE_SOURCE=/usr/src/akmods/yeetmouse-%{version}
EOF

%post
# Trigger akmod build for current kernel
/usr/sbin/akmods --force --kernels $(uname -r) || true
/usr/sbin/depmod -a || true
/sbin/modprobe yeetmouse || true

%preun
# Unload module before uninstall
/sbin/modprobe -r yeetmouse 2>/dev/null || true

%files
/usr/src/akmods/yeetmouse-%{version}
/etc/akmods/yeetmouse.conf

%changelog
* Thu Nov 06 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Initial akmod package for YeetMouse
