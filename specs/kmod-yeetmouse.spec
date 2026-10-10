%global debug_package %{nil}
%global kmod_name yeetmouse

%global commit %{?commit}%{!?commit:78dcd0d573bedd5dd7b9e29e9162b28c9eb2fd7b}
%global shortcommit %{?shortcommit}%{!?shortcommit:78dcd0d}
# Snapshot version, Fedora Versioning guidelines (Snapshots):
# Version is 0^<upstream committer date, UTC, YYYYMMDD>git<shortcommit>
# (upstream has no releases, so the base is 0). Release counts packaging
# changes for one Version and goes back to 1 when the pin changes. The
# upstream poller sets snapdate and the pin, the kernel poller raises the
# kmod Release, and a packaging-only change raises Release by hand
# (check-and-build.yml fails the push otherwise). See
# .github/scripts/spec_version.py.
%global snapdate 20260803

Name:           %{kmod_name}-kmod
Version:        0^%{snapdate}git%{shortcommit}
Release:        1%{?dist}
Summary:        YeetMouse mouse acceleration kernel module
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz
Source1:        config.h
# CORRECTED: this file exists in the real repo at the ROOT (config.h), not under specs/. My
# earlier check of specs/config.h (404) was the wrong path, not evidence the file is missing
# -- confirmed by browsing the real repo tree directly. The actual file is now copied to
# specs-real/config.h alongside this spec, matching the real repo's structure where %prep
# would reference it the same way the CLI build process already does today.

BuildRequires:  %{_bindir}/kmodtool
BuildRequires:  kernel-devel
BuildRequires:  gcc
BuildRequires:  make
# CONFIRMED by live COPR build (design doc 3.3, item 3): resolve kernel-devel's version via
# rpm -q embedded in the macro expansion itself, evaluated fresh wherever this spec is
# actually parsed -- never pin an externally-resolved version string.
%global kmodtool_for_kernels %(rpm -q --qf '[%%{VERSION}-%%{RELEASE}.%%{ARCH} ]' kernel-devel 2>/dev/null)
%if "%{kmodtool_for_kernels}" == ""
%{error:kernel-devel must be installed before kmodtool is evaluated}
%endif
%{expand:%(kmodtool --target %{_target_cpu} --kmodname %{kmod_name} --for-kernels "%{kmodtool_for_kernels}" 2>&1)}

# CONFIRMED REQUIRED by real multi-kernel install testing (design doc 4, item 2b): kmodtool's
# generated per-kernel %%package stanza unconditionally emits
# Requires: %%{kmod_name}-kmod-common -- this package must exist as a real, separately
# installable RPM, even though it carries no files of its own.
%package -n %{kmod_name}-kmod-common
Summary:        Common package required by kmodtool-generated per-kernel subpackages
BuildArch:      noarch
%description -n %{kmod_name}-kmod-common
Metadata-only package. kmodtool's generated per-kernel %%package stanza unconditionally
requires %%{kmod_name}-kmod-common; this package exists solely to satisfy that dependency so
multiple kernel-version kmod subpackages can be installed together without a missing-package
error. Confirmed required by direct install-time testing, not inferred from kmodtool's docs.

%description
Kernel module for the YeetMouse mouse acceleration driver. Provides %{kmod_name}.ko, built
separately for each installed kernel version. Runtime configuration lives in
/etc/yeetmouse.conf, owned by the yeetmouse package (not this one -- see design doc 3.3b: a
per-kernel subpackage must never own a file shared across kernel ABIs, since more than one
kernel's subpackage can be installed at once).

%prep
%{?kmodtool_check}
%autosetup -n YeetMouse-%{commit}
for kernel_version in %{?kernel_versions}; do
    kv="${kernel_version%%___*}"
    cp -a driver _kmod_build_${kv}
    cp %{SOURCE1} _kmod_build_${kv}/config.h
done

%build
for kernel_version in %{?kernel_versions}; do
    kv="${kernel_version%%___*}"
    srcdir="${kernel_version##*___}"
    pushd _kmod_build_${kv}/
    make -C "${srcdir}" M="${PWD}" modules
    popd
done

%install
for kernel_version in %{?kernel_versions}; do
    kv="${kernel_version%%___*}"
    install -D -m 0644 _kmod_build_${kv}/%{kmod_name}.ko \
        %{buildroot}%{kmodinstdir_prefix}/${kv}%{kmodinstdir_postfix}/%{kmod_name}.ko
done

# No %%files, %%post or %%postun for the main package. kmodtool already generates
# them for each kmod-yeetmouse-<kernel> package: its %%files owns
# /lib/modules/<kernel>/extra/yeetmouse/ and its scriptlets run depmod for that
# kernel. A main-package %%files made rpmbuild emit an extra binary package,
# yeetmouse-kmod, that shipped the same .ko with no kernel requirement and
# satisfied yeetmouse-gui's Requires: yeetmouse-kmod on its own. Confirmed on
# probe build 11104363.

%files -n %{kmod_name}-kmod-common
# intentionally empty -- this package exists only to satisfy kmodtool's generated Requires

%changelog
* Sat Oct 10 2026 abirkel - 0^20260803git78dcd0d-1
- Switch to Fedora snapshot versioning: Version is
  0^<snapshot date>git<shortcommit> and Release is a packaging counter
  that goes back to 1 when the pin changes. This replaces the pkgserial
  scheme below.

* Sat Oct 10 2026 abirkel - 0-2.20260803git78dcd0d
- Drop the main package's files list and depmod scriptlets. kmodtool
  generates both for each kernel package, and the main files list made
  rpmbuild emit a stray yeetmouse-kmod binary package with the same .ko
  and no kernel requirement.
* Sat Oct 10 2026 abirkel - 0-1.20260803git78dcd0d
- New versioning for the COPR project: Release is pkgserial.commitdate
  git shortcommit, and pkgserial alone orders builds. COPR SCM builds use
  the spec's Release as written, so the old release-number placeholder
  never changed between builds. No Epoch: nothing needs to outrank the old
  GitHub-era packages, so the Epoch bump planned in the entry below was
  dropped.
* Sun Oct 04 2026 abirkel - 0-1
- Rewritten for COPR: chroot-provisioned kmodtool/kernel-devel (no more external pre-install
  step), kernel-devel resolved via embedded rpm -q at spec-parse time, %files lists the
  BRP-compressed .ko.xz, new yeetmouse-kmod-common package to satisfy kmodtool's generated
  per-kernel Requires, /etc/yeetmouse.conf ownership moved to the yeetmouse package (see
  yeetmouse.spec), release-number script replaced by an Epoch bump at cutover time (see design
  doc Section 3.5). Every claim in this spec traces to a real COPR build or disposable-VM test
  in yeetmouse-copr-design.md -- read that doc's revision log before changing this file.
