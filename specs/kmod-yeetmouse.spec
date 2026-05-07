# Build kmod package for a specific kernel version
# Usage: rpmbuild --define 'kernel_version 6.11.8-300.fc41.x86_64' -ba kmod-yeetmouse.spec

# kernel_version must be defined at build time
%{!?kernel_version: %{error: kernel_version must be defined. Use: rpmbuild --define 'kernel_version X.X.X-XXX.fcXX.x86_64'}}

%global debug_package %{nil}
%global kmod_name yeetmouse
%global commit %{?commit}%{!?commit:99844bbd786d612657d892cac2f663d940fd3d62}
%global shortcommit %{?shortcommit}%{!?shortcommit:99844bb}
%global commit_timestamp %{?commit_timestamp}%{!?commit_timestamp:202412091624}

Name:           kmod-%{kmod_name}-%{kernel_version}
Version:        0
Release:        %{?release}%{!?release:1}.%{commit_timestamp}g%{shortcommit}%{?dist}
Summary:        Kernel module for YeetMouse mouse acceleration driver

License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz
Source1:        config.h
Source2:        yeetmouse.conf

# Note: kernel-devel is installed manually in the build workflow
# before rpmbuild runs, so it's not listed in BuildRequires
BuildRequires:  gcc
BuildRequires:  make

Provides:       kmod-%{kmod_name} = %{version}-%{release}
Provides:       %{kmod_name}-kmod = %{version}-%{release}
Provides:       kernel-modules-for-kernel = %{kernel_version}

Requires:       kernel-uname-r = %{kernel_version}
Requires:       yeetmouse

%description
Kernel module for the YeetMouse mouse acceleration driver, built for kernel %{kernel_version}.

YeetMouse is a mouse acceleration driver for Linux that provides customizable mouse
acceleration curves and parameters through a kernel module and CLI tool.

This package contains the pre-compiled kernel module for kernel %{kernel_version}.
Settings are applied at boot via yeetmouse.service using /etc/yeetmouse.conf.

%prep
%autosetup -n YeetMouse-%{commit}

%build
# Use custom config.h from Source1 (sets compile-time defaults only;
# runtime settings are applied from /etc/yeetmouse.conf via yeetmousectl)
cp %{SOURCE1} driver/config.h

# Build the kernel module for the specified kernel version
make V=1 %{?_smp_mflags} \
    -C /usr/src/kernels/%{kernel_version} \
    M=${PWD}/driver \
    modules

%install
# Install the kernel module
install -D -m 644 driver/%{kmod_name}.ko \
    %{buildroot}/usr/lib/modules/%{kernel_version}/extra/%{kmod_name}/%{kmod_name}.ko

# Install runtime configuration (noreplace: upgrades preserve user edits)
install -D -m 644 %{SOURCE2} \
    %{buildroot}/etc/yeetmouse.conf

%files
/usr/lib/modules/%{kernel_version}/extra/%{kmod_name}/%{kmod_name}.ko
%config(noreplace) /etc/yeetmouse.conf

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
* Thu May 07 2026 YeetMouse Builder <builder@yeetmouse.local> - 0-1
- Add /etc/yeetmouse.conf (runtime config, noreplace) translated from config.h
- Add Requires: yeetmouse to ensure yeetmousectl and yeetmouse.service are present
- Settings now applied at runtime via yeetmousectl instead of compile-time config.h

* Wed Dec 25 2024 YeetMouse Builder <builder@yeetmouse.local> - 0-1
- Fix package naming to include kernel version in Name field
- Add kernel-modules-for-kernel provide for proper rpm-ostree detection
- Add kernel-uname-r requirement for kernel version matching
- This fixes rpm-ostree selecting wrong kernel module version

* Wed Nov 20 2024 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Convert from akmod to kmod package for atomic/ostree distros
- Build for specific kernel version passed via macro
- Remove kernel dependency from Requires (kernel module is version-specific)
- Support commit-based versioning for development builds
