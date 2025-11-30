# Build kmod package for a specific kernel version
# Usage: rpmbuild --define 'kernel_version 6.11.8-300.fc41.x86_64' -ba kmod-yeetmouse.spec

# kernel_version must be defined at build time
%{!?kernel_version: %{error: kernel_version must be defined. Use: rpmbuild --define 'kernel_version X.X.X-XXX.fcXX.x86_64'}}

%global debug_package %{nil}
%global kmod_name yeetmouse
%global commit %{?commit}%{!?commit:99844bbd786d612657d892cac2f663d940fd3d62}
%global shortcommit %{?shortcommit}%{!?shortcommit:99844bb}
# Convert kernel version for RPM filename: replace - with _ and remove arch suffix
# Note: RPM will add .x86_64 automatically to binary packages
%global kernel_version_rpm %(echo %{kernel_version} | sed 's/-/_/g' | sed 's/\\.x86_64$//')

Name:           kmod-%{kmod_name}
Version:        %{?version}%{!?version:0.9.2}
Release:        %{?release}%{!?release:1}.git%{shortcommit}%{?dist}.%{kernel_version_rpm}
Summary:        Kernel module for YeetMouse mouse acceleration driver

License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz

# Note: kernel-devel is installed manually in the build workflow
# before rpmbuild runs, so it's not listed in BuildRequires
BuildRequires:  gcc
BuildRequires:  make

Provides:       kmod-yeetmouse = %{version}-%{release}
Provides:       %{kmod_name}-kmod = %{version}-%{release}

%description
Kernel module for the YeetMouse mouse acceleration driver, built for kernel %{kernel_version}.

YeetMouse is a mouse acceleration driver for Linux that provides customizable mouse
acceleration curves and parameters through a kernel module and CLI tool.

This package contains the pre-compiled kernel module for a specific kernel version.

%prep
%autosetup -n YeetMouse-%{commit}

%build
# Copy config.sample.h to config.h if config.h doesn't exist
if [ ! -f driver/config.h ]; then
    cp driver/config.sample.h driver/config.h
fi

# Build the kernel module for the specified kernel version
make V=1 %{?_smp_mflags} \
    -C /usr/src/kernels/%{kernel_version} \
    M=${PWD}/driver \
    modules

%install
# Install the kernel module
install -D -m 644 driver/%{kmod_name}.ko \
    %{buildroot}/usr/lib/modules/%{kernel_version}/extra/%{kmod_name}/%{kmod_name}.ko

%files
/usr/lib/modules/%{kernel_version}/extra/%{kmod_name}/%{kmod_name}.ko

%post
# Run depmod to update module dependencies
if [ -x /usr/sbin/depmod ]; then
    /usr/sbin/depmod -a %{kernel_version} || :
fi

%postun
# Run depmod after uninstall
if [ $1 -eq 0 ]; then
    if [ -x /usr/sbin/depmod ]; then
        /usr/sbin/depmod -a %{kernel_version} || :
    fi
fi

%changelog
* Wed Nov 20 2024 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Convert from akmod to kmod package for atomic/ostree distros
- Build for specific kernel version passed via macro
- Remove kernel dependency from Requires (kernel module is version-specific)
- Support commit-based versioning for development builds
