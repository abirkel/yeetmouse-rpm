%global debug_package %{nil}
%global kmod_name yeetmouse

%global commit %{?commit}%{!?commit:99844bbd786d612657d892cac2f663d940fd3d62}
%global shortcommit %{?shortcommit}%{!?shortcommit:99844bb}

Name:           %{kmod_name}-kmod
Version:        0
Release:        %{?release}%{!?release:1}%{?dist}
# Epoch: see design doc Section 3.5 -- bump to 1 at the actual COPR cutover point, confirmed
# by direct rpmdev-vercmp testing to be the only safe way to guarantee every COPR-built NEVR
# outranks every already-published GitHub-Releases-era NEVR regardless of Release string
# shape. Left commented out here since this spec is not yet the live cutover build; uncomment
# (Epoch: 1) when this actually replaces the GitHub Actions pipeline.
# Epoch:          1
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

# CONFIRMED by direct build-log diagnostic (design doc 3.3, item following the probe
# failure): Fedora's standard BRP kmod-compression step renames <name>.ko to <name>.ko.xz
# between %install and %files evaluation. %files must list the compressed name. Confirm this
# extension against each target Fedora release's actual BRP config rather than assuming .xz
# is permanent -- Fedora has changed kmod compression algorithms/extensions across releases
# historically (design doc 4, item 1).
%files
%{kmodinstdir_prefix}/*%{kmodinstdir_postfix}/%{kmod_name}.ko.xz

%files -n %{kmod_name}-kmod-common
# intentionally empty -- this package exists only to satisfy kmodtool's generated Requires

%post
for kernel_version in %{?kernel_versions}; do
    /usr/sbin/depmod -a "${kernel_version%%___*}" || :
done

%postun
if [ $1 -eq 0 ]; then
    for kernel_version in %{?kernel_versions}; do
        /usr/sbin/depmod -a "${kernel_version%%___*}" || :
    done
fi

%changelog
* Sun Oct 04 2026 abirkel - 0-1
- Rewritten for COPR: chroot-provisioned kmodtool/kernel-devel (no more external pre-install
  step), kernel-devel resolved via embedded rpm -q at spec-parse time, %files lists the
  BRP-compressed .ko.xz, new yeetmouse-kmod-common package to satisfy kmodtool's generated
  per-kernel Requires, /etc/yeetmouse.conf ownership moved to the yeetmouse package (see
  yeetmouse.spec), release-number script replaced by an Epoch bump at cutover time (see design
  doc Section 3.5). Every claim in this spec traces to a real COPR build or disposable-VM test
  in yeetmouse-copr-design.md -- read that doc's revision log before changing this file.
