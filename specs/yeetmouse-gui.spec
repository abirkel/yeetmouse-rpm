%global debug_package %{nil}
%global commit 99844bbd786d612657d892cac2f663d940fd3d62
%global shortcommit 99844bb

Name:           yeetmouse-gui
Version:        0.9.2
Release:        %{?release_number}%{!?release_number:1}.git%{shortcommit}%{?dist}
Summary:        GUI application for YeetMouse mouse acceleration configuration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        %{url}/archive/%{commit}/YeetMouse-%{commit}.tar.gz

BuildRequires:  gcc-c++
BuildRequires:  make
BuildRequires:  glfw-devel
BuildRequires:  mesa-libGL-devel

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
* Fri Nov 07 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1.git99844bb
- Update to git snapshot 99844bb
- Fix spec to use proper git snapshot source URL
- Add commented-out desktop file integration (optional)

* Thu Nov 06 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Initial GUI package for YeetMouse
