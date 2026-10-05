%global debug_package %{nil}
%global commit %{?commit}%{!?commit:99844bbd786d612657d892cac2f663d940fd3d62}
%global shortcommit %{?shortcommit}%{!?shortcommit:99844bb}

Name:           yeetmouse
Version:        0
Release:        %{?release}%{!?release:1}%{?dist}
# Epoch: see kmod-yeetmouse.spec's comment and design doc Section 3.5 -- bump both specs'
# Epoch together at the actual COPR cutover point, not just this one.
# Epoch:          1
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
BuildRequires:  glfw-devel
BuildRequires:  mesa-libGL-devel
BuildRequires:  systemd-rpm-macros
Requires:       glfw
Requires:       mesa-libGL
%{?systemd_requires}
%{?sysusers_requires_compat}

%description
Userspace components for the YeetMouse mouse acceleration driver. Includes:
- yeetmousectl: CLI tool to apply and save acceleration settings
- yeetmouse-gui: graphical configuration interface
- yeetmouse.service: systemd service that applies /etc/yeetmouse.conf at boot

/etc/yeetmouse.conf is owned by THIS package, not any kmod-yeetmouse-<kernel-version>
subpackage (see design doc Section 3.3b, confirmed by a real multi-package install test):
more than one kernel's kmod subpackage can be installed at once during a kernel-upgrade
window, and a shared config file must not be claimed by more than one of them.

%prep
%setup -q -n YeetMouse-%{commit}

%build
make yeetmousectl
make GUI

%install
install -D -m 755 tools/yeetmousectl/yeetmousectl \
    %{buildroot}%{_bindir}/yeetmousectl
install -D -m 755 gui/YeetMouseGui \
    %{buildroot}%{_bindir}/yeetmouse-gui
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
%{_bindir}/yeetmouse-gui
%{_unitdir}/yeetmouse.service
%{_prefix}/lib/systemd/system-preset/50-yeetmouse.preset
%{_sysusersdir}/yeetmouse.conf
%config(noreplace) /etc/yeetmouse.conf

%changelog
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
