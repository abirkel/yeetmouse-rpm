%global debug_package %{nil}
%global commit %{?commit}%{!?commit:99844bbd786d612657d892cac2f663d940fd3d62}
%global shortcommit %{?shortcommit}%{!?shortcommit:99844bb}
%global commit_timestamp %{?commit_timestamp}%{!?commit_timestamp:202412091624}

Name:           yeetmouse
Version:        0
Release:        %{?release}%{!?release:1}.%{commit_timestamp}g%{shortcommit}%{?dist}
Summary:        CLI tool and systemd service for YeetMouse mouse acceleration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz
Source1:        yeetmouse.service
Source2:        yeetmouse-preset.conf

BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  glfw-devel
BuildRequires:  mesa-libGL-devel
BuildRequires:  systemd-rpm-macros

Requires:       glfw
Requires:       mesa-libGL
%{?systemd_requires}

%description
Userspace components for the YeetMouse mouse acceleration driver.

Includes:
- yeetmousectl: CLI tool to apply and save acceleration settings
- yeetmouse-gui: graphical configuration interface
- yeetmouse.service: systemd service that applies /etc/yeetmouse.conf at boot

%prep
%setup -q -n YeetMouse-%{commit}

%build
# Build yeetmousectl CLI tool
make yeetmousectl

# Build GUI application
make GUI

%install
# Install yeetmousectl binary
install -D -m 755 tools/yeetmousectl/yeetmousectl \
    %{buildroot}%{_bindir}/yeetmousectl

# Install GUI binary
install -D -m 755 gui/YeetMouseGui \
    %{buildroot}%{_bindir}/yeetmouse-gui

# Install systemd service
install -D -m 644 %{SOURCE1} \
    %{buildroot}%{_unitdir}/yeetmouse.service

# Install systemd preset so the service is enabled by default
# (required for rpm-ostree/atomic systems where scriptlets don't run)
install -D -m 644 %{SOURCE2} \
    %{buildroot}%{_prefix}/lib/systemd/system-preset/50-yeetmouse.preset

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

%changelog
* Thu May 07 2026 YeetMouse Builder <builder@yeetmouse.local> - 0-2
- Ship 50-yeetmouse.preset so service auto-enables on rpm-ostree/atomic installs

* Thu May 07 2026 YeetMouse Builder <builder@yeetmouse.local> - 0-1
- Add yeetmousectl CLI tool (required for runtime config apply)
- Add yeetmouse.service systemd unit (applies /etc/yeetmouse.conf at boot)
- Update summary and description to reflect new userspace components
- Add systemd-rpm-macros BuildRequires and systemd scriptlets

* Fri Nov 21 2025 github-actions[bot] <github-actions[bot]@users.noreply.github.com> - 0.9.2-3.git99844bb
- Rebuild for kernel compatibility

* Sun Nov 09 2025 github-actions[bot] <github-actions[bot]@users.noreply.github.com> - 0.9.2-2.git99844bb
- Rebuild for kernel compatibility

* Fri Nov 07 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1.git99844bb
- Update to git snapshot 99844bb
- Fix spec to use proper git snapshot source URL
- Add commented-out desktop file integration (optional)
- Add kernel module dependency (kmod-yeetmouse)

* Thu Nov 06 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Initial GUI package for YeetMouse
