%global debug_package %{nil}

Name:           kmod-yeetmouse
Version:        0.9.2
Release:        %{?release_number}%{!?release_number:1}%{?dist}
Summary:        Kernel module for YeetMouse mouse acceleration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        yeetmouse-%{version}.tar.gz

BuildRequires:  kernel-devel
BuildRequires:  gcc
BuildRequires:  make

Requires:       kernel

# Disable debug package generation for kernel modules
%global debug_package %{nil}

%description
YeetMouse is a kernel module that provides customizable mouse acceleration.
This package provides the kmod version built for a specific kernel version.
The module must be rebuilt when the kernel is updated.

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
# Find installed kernel-devel version
KVER=$(rpm -q kernel-devel --qf '%%{VERSION}-%%{RELEASE}.%%{ARCH}\n' | head -1)

# Install kernel module
mkdir -p %{buildroot}/lib/modules/${KVER}/extra/yeetmouse
install -m 644 driver/yeetmouse.ko %{buildroot}/lib/modules/${KVER}/extra/yeetmouse/

%post
# Update module dependencies
KVER=$(rpm -q kernel-devel --qf '%%{VERSION}-%%{RELEASE}.%%{ARCH}\n' | head -1)
/usr/sbin/depmod -a ${KVER} || true
/sbin/modprobe yeetmouse || true

%preun
# Unload module before uninstall
/sbin/modprobe -r yeetmouse 2>/dev/null || true

%files
/lib/modules/*/extra/yeetmouse/yeetmouse.ko

%changelog
* Thu Nov 06 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Initial kmod package for YeetMouse
