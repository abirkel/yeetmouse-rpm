%global debug_package %{nil}
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

Name:           yeetmouse
Version:        0^%{snapdate}git%{shortcommit}
Release:        1%{?dist}
Summary:        CLI tool and systemd service for YeetMouse mouse acceleration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz
Source1:        yeetmouse.service
Source2:        yeetmouse-preset.conf
Source3:        yeetmouse-sysusers.conf
Source4:        yeetmouse.conf

BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  systemd-rpm-macros
%{?systemd_requires}
%{?sysusers_requires_compat}

%description
Userspace CLI tool and systemd service for the YeetMouse mouse acceleration driver. Includes:
- yeetmousectl: CLI tool to apply and save acceleration settings
- yeetmouse.service: systemd service that applies /etc/yeetmouse.conf at boot

The graphical configuration interface is packaged separately as yeetmouse-gui.

/etc/yeetmouse.conf is owned by THIS package, not any kmod-yeetmouse-<kernel-version>
subpackage (see design doc Section 3.3b, confirmed by a real multi-package install test):
more than one kernel's kmod subpackage can be installed at once during a kernel-upgrade
window, and a shared config file must not be claimed by more than one of them.

%prep
%setup -q -n YeetMouse-%{commit}

%build
make yeetmousectl

%install
install -D -m 755 tools/yeetmousectl/yeetmousectl \
    %{buildroot}%{_bindir}/yeetmousectl
install -D -m 644 %{SOURCE1} \
    %{buildroot}%{_unitdir}/yeetmouse.service
install -D -m 644 %{SOURCE2} \
    %{buildroot}%{_prefix}/lib/systemd/system-preset/50-yeetmouse.preset
install -D -m 644 %{SOURCE3} \
    %{buildroot}%{_sysusersdir}/yeetmouse.conf
install -D -m 644 %{SOURCE4} \
    %{buildroot}/etc/yeetmouse.conf

%pre
%sysusers_create_compat %{SOURCE3}

%post
%systemd_post yeetmouse.service

%preun
%systemd_preun yeetmouse.service

%postun
%systemd_postun_with_restart yeetmouse.service

%files
%{_bindir}/yeetmousectl
%{_unitdir}/yeetmouse.service
%{_prefix}/lib/systemd/system-preset/50-yeetmouse.preset
%{_sysusersdir}/yeetmouse.conf
%config(noreplace) /etc/yeetmouse.conf

%changelog
* Sat Oct 10 2026 abirkel - 0^20260803git78dcd0d-1
- Switch to Fedora snapshot versioning: Version is
  0^<snapshot date>git<shortcommit> and Release is a packaging counter
  that goes back to 1 when the pin changes. This replaces the pkgserial
  scheme below.

* Sat Oct 10 2026 abirkel - 0-1.20260803git78dcd0d
- New versioning for the COPR project, same scheme as kmod-yeetmouse:
  Release is pkgserial.commitdate git shortcommit, no Epoch. The Epoch
  bump planned in the 0-4 entry below was dropped.
* Thu Oct 08 2026 abirkel - 0-5
- Split the GUI back out into its own yeetmouse-gui package: this package shipping
  /usr/bin/yeetmouse-gui at the same time as a separate yeetmouse-gui package was a real
  RPM file-ownership conflict (yeetmouse-gui.spec, orphaned since before the COPR migration,
  claims the same path). Reviewed by gpt-5.6-terra (option (a): CLI-only, GUI is
  yeetmouse-gui's sole responsibility). Dropped the GUI build/install lines, the GUI entry
  from the files list, and the glfw/mesa-libGL BuildRequires/Requires that existed only for
  it -- confirmed safe by reading ConfigHelper.cpp/DriverHelper.cpp/CustomCurve.cpp directly,
  none include GL/GLFW headers. Also bumped the stale commit pin (99844bb, pre-dates
  upstream's tools/yeetmousectl/ restructuring) to 78dcd0d5, the commit this repo's own
  version-tracking already uses.
* Sun Oct 04 2026 abirkel - 0-4
- Move /etc/yeetmouse.conf ownership here from kmod-yeetmouse (design doc Section 3.3b):
  confirmed by a real multi-package install test that the old per-kernel-subpackage ownership
  would conflict when two kernel ABIs' kmod packages are installed at once. Release-number
  script replaced by an Epoch bump at cutover time (see design doc Section 3.5).
* Mon Aug 31 2026 abirkel - 0-3
- Create the 'yeetmouse' group via sysusers.d. yeetmouse.service chowns
  /sys/module/yeetmouse/parameters/* to it, but the package never created it, so the unit
  failed on every boot with "chown: invalid group: 'root:yeetmouse'" and no mouse
  configuration was ever applied.
* Thu May 07 2026 YeetMouse Builder - 0-2
- Ship 50-yeetmouse.preset so service auto-enables on rpm-ostree/atomic installs
* Thu May 07 2026 YeetMouse Builder - 0-1
- Add yeetmousectl CLI tool (required for runtime config apply)
- Add yeetmouse.service systemd unit (applies /etc/yeetmouse.conf at boot)
- Update summary and description to reflect new userspace components
- Add systemd-rpm-macros BuildRequires and systemd scriptlets
