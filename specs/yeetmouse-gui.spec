%global debug_package %{nil}
%global commit %{?commit}%{!?commit:78dcd0d573bedd5dd7b9e29e9162b28c9eb2fd7b}
%global shortcommit %{?shortcommit}%{!?shortcommit:78dcd0d}
# Upstream committer date (UTC) of the pinned commit. Informational only.
%global commitdate 20260803
# Build order counter, only ever raised. See kmod-yeetmouse.spec and
# .github/scripts/spec_version.py.
%global pkgserial 1

Name:           yeetmouse-gui
Version:        0
Release:        %{pkgserial}.%{commitdate}git%{shortcommit}%{?dist}
Summary:        GUI application for YeetMouse mouse acceleration configuration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz

BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  glfw-devel
BuildRequires:  mesa-libGL-devel

# yeetmouse-kmod is provided by every kernel-specific kmod-yeetmouse-<kernel>
# package. Nothing provides plain "kmod-yeetmouse".
Requires:       yeetmouse-kmod
Requires:       yeetmouse
Requires:       glfw
Requires:       mesa-libGL

%description
YeetMouse GUI is a graphical configuration tool for the YeetMouse kernel module.
It provides an intuitive interface for configuring mouse acceleration parameters,
custom curves, and other settings.

%prep
%setup -q -n YeetMouse-%{commit}

%build
# Build GUI application
cd gui
make

%install
# Install GUI binary
mkdir -p %{buildroot}%{_bindir}
install -m 755 gui/YeetMouseGui %{buildroot}%{_bindir}/yeetmouse-gui

# Optional: Desktop integration (commented out by default)
# Uncomment the following lines to add desktop menu entry
#mkdir -p %%{buildroot}%%{_datadir}/applications
#cat > %%{buildroot}%%{_datadir}/applications/yeetmouse-gui.desktop <<EOF
#[Desktop Entry]
#Type=Application
#Name=YeetMouse GUI
#Comment=Configure YeetMouse mouse acceleration settings
#Exec=yeetmouse-gui
#Icon=input-mouse
#Terminal=true
#Categories=System;Settings;
#Keywords=mouse;acceleration;input;
#EOF

%files
%{_bindir}/yeetmouse-gui
# Uncomment if desktop file is enabled:
#%%{_datadir}/applications/yeetmouse-gui.desktop

%changelog
* Sat Oct 10 2026 abirkel - 0-1.20260803git78dcd0d
- New versioning for the COPR project, same scheme as kmod-yeetmouse:
  Version 0, Release is pkgserial.commitdate git shortcommit, no Epoch.
- Require yeetmouse-kmod instead of kmod-yeetmouse, which no package
  provides.
- Commit pin is now overridable with --define, like the other specs.
* Fri Nov 21 2025 github-actions[bot]   <github-actions[bot]@users.noreply.github.com> - 0.9.2-3.git99844bb
- Rebuild for kernel compatibility
* Sun Nov 09 2025 github-actions[bot]   <github-actions[bot]@users.noreply.github.com> - 0.9.2-2.git99844bb
- Rebuild for kernel compatibility
* Fri Nov 07 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1.git99844bb
- Update to git snapshot 99844bb
- Fix spec to use proper git snapshot source URL
- Add commented-out desktop file integration (optional)
- Add kernel module dependency (akmod or kmod)

* Thu Nov 06 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Initial GUI package for YeetMouse
