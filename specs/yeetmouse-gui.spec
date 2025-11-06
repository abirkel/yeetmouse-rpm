Name:           yeetmouse-gui
Version:        0.9.2
Release:        1%{?dist}
Summary:        GUI application for YeetMouse mouse acceleration configuration
License:        GPL-2.0-or-later
URL:            https://github.com/AndyFilter/YeetMouse
Source0:        yeetmouse-%{version}.tar.gz

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
%setup -q -n yeetmouse

%build
# Build GUI application
cd gui
make

%install
# Install GUI binary
mkdir -p %{buildroot}%{_bindir}
install -m 755 gui/YeetMouseGui %{buildroot}%{_bindir}/yeetmouse-gui

%post
echo "YeetMouse GUI installed successfully"
echo "Run 'yeetmouse-gui' to configure YeetMouse settings"

%files
%{_bindir}/yeetmouse-gui

%changelog
* Thu Nov 06 2025 YeetMouse Builder <builder@yeetmouse.local> - 0.9.2-1
- Initial GUI package for YeetMouse
