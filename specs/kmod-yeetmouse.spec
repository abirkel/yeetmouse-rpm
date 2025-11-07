%global debug_package %{nil}
%global commit 99844bbd786d612657d892cac2f663d940fd3d62
%global shortcommit 99844bb

Name:           kmod-yeetmouse
Version:        0.9.2
Release:        %{?release_number}%{!?release_number:1}.git%{shortcommit}%{?dist}
Summary:        Kernel module for YeetMouse mouse acceleration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz

BuildRequires:  kernel-devel
BuildRequires:  gcc
BuildRequires:  make

Requires:       kernel

%description
YeetMouse is a kernel module that provides customizable mouse acceleration.
This package provides the kmod version built for a specific kernel version.
The module must be rebuilt when the kernel is updated.

%prep
%setup -q -n YeetMouse-%{commit}

%build
# Copy sample config if config.h doesn't exist
if [ ! -f driver/config.h ]; then
    cp driver/config.sample.h driver/config.h
fi

# Build kernel module for current kernel-devel
KVER=$(ls -1 /usr/src/kernels | head -1)

# Build kernel module
cd driver
make -C /usr/src/kernels/${KVER} M=$(pwd) modules

%install
# Get kernel version from build
KVER=$(ls -1 /usr/src/kernels | head -1)

# Install kernel module
mkdir -p %{buildroot}/lib/modules/${KVER}/extra/yeetmouse
install -m 644 driver/yeetmouse.ko %{buildroot}/lib/modules/${KVER}/extra/yeetmouse/

%post
# Update module dependencies for running kernel
/usr/sbin/depmod -a || true
/sbin/modprobe yeetmouse || true

%preun
# Unload module before uninstall
/sbin/modprobe -r yeetmouse 2>/dev/null || true

%files
/lib/modules/*/extra/yeetmouse/yeetmouse.ko

%changelog
* Fri Nov 07 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1.git99844bb
- Update to git snapshot 99844bb
- Fix spec to use proper git snapshot source URL
- Fix KVER detection to use installed kernels directory
- Simplify post-install script to use system's running kernel

* Thu Nov 06 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Initial kmod package for YeetMouse
