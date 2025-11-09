%global debug_package %{nil}
%global commit 99844bbd786d612657d892cac2f663d940fd3d62
%global shortcommit 99844bb

Name:           akmod-yeetmouse
Version:        0.9.2
Release:        2.git%{shortcommit}%{?dist}
Summary:        Automatic kernel module for YeetMouse mouse acceleration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz

BuildRequires:  akmods

Requires:       akmods
Requires:       kernel-devel

%description
YeetMouse is a kernel module that provides customizable mouse acceleration.
This package provides the akmod (automatic kernel module) version that
automatically rebuilds the module when the kernel is updated.

%prep
%setup -q -n YeetMouse-%{commit}

%build
# Prepare source files only - akmods will compile on target system
if [ ! -f driver/config.h ]; then
    cp driver/config.sample.h driver/config.h
fi

%install
# Install source files to akmods directory
mkdir -p %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver
mkdir -p %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/FixedMath

# Copy source files for akmod rebuilds
cp -r driver/*.c %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/
cp -r driver/*.h %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/
cp -r driver/FixedMath/*.h %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/FixedMath/
cp driver/Makefile %{buildroot}/usr/src/akmods/yeetmouse-%{version}/driver/
cp shared_definitions.h %{buildroot}/usr/src/akmods/yeetmouse-%{version}/
cp Makefile %{buildroot}/usr/src/akmods/yeetmouse-%{version}/

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

%changelog
* Sun Nov 09 2025 github-actions[bot]   <github-actions[bot]@users.noreply.github.com> - 0.9.2-2.git99844bb
- Rebuild for kernel compatibility
* Fri Nov 07 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1.git99844bb
- Update to git snapshot 99844bb
- Fix spec to use proper git snapshot source URL

* Thu Nov 06 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Initial akmod package for YeetMouse
