# YeetMouse RPM Packaging

[![Latest Release](https://img.shields.io/github/v/release/abirkel/yeetmouse-rpm?label=Latest%20Release&color=blue)](https://github.com/abirkel/yeetmouse-rpm/releases/latest)
[![Build Status](https://img.shields.io/github/actions/workflow/status/abirkel/yeetmouse-rpm/build-rpm.yml?branch=main&label=Build)](https://github.com/abirkel/yeetmouse-rpm/actions/workflows/build-rpm.yml)
[![Platform](https://img.shields.io/badge/Platform-Fedora%20%7C%20RPM-294172?logo=fedora)](https://github.com/abirkel/yeetmouse-rpm)

RPM packages for the [YeetMouse](https://github.com/AndyFilter/YeetMouse) mouse acceleration driver for Fedora and RPM-based Linux distributions.

## Overview

This repository provides automated RPM packaging for YeetMouse, a customizable mouse acceleration driver consisting of a kernel module and GUI configuration tool. Packages are built automatically via GitHub Actions when new YeetMouse commits are detected.

## Packages

This repository provides three packages:

- **akmod-yeetmouse**: Automatic kernel module package that rebuilds for new kernels using akmods
- **kmod-yeetmouse**: Pre-compiled kernel module for specific kernel versions (optional)
- **yeetmouse-gui**: GUI application for configuring mouse acceleration parameters

### Akmod vs Kmod

**Akmod (Recommended for most users)**:
- Automatically rebuilds the kernel module when your kernel updates
- Works across kernel updates without manual intervention
- Requires kernel-devel and build tools on your system
- Slightly longer initial installation time (builds on first install)

**Kmod (Alternative)**:
- Pre-compiled kernel module for specific kernel versions
- Faster installation (no compilation needed)
- Must match your exact kernel version
- Requires new package when kernel updates

For most users, the akmod package is recommended as it provides automatic compatibility with kernel updates.

## Installation

**Prerequisites**: Fedora or compatible RPM-based distribution (x86_64)

### Repository Setup

Add the yeetmouse repository to your system:

```bash
# Download and install the repository configuration
sudo curl -L https://raw.githubusercontent.com/abirkel/yeetmouse-rpm/main/yeetmouse.repo \
  -o /etc/yum.repos.d/yeetmouse.repo
```

The GPG public key will be automatically imported when you first install a package from this repository.

### Package Installation

Install YeetMouse and its dependencies:

```bash
# Install YeetMouse with akmod (recommended)
sudo dnf install akmod-yeetmouse yeetmouse-gui

# Alternative: Install with pre-compiled kmod (if available for your kernel)
sudo dnf install kmod-yeetmouse yeetmouse-gui
```

The akmod system will build the kernel module for your current kernel during installation. This may take a few minutes on first install.

### Post-Installation

After installation, complete these steps to start using YeetMouse:

**1. Verify Kernel Module is Loaded**

Check that the yeetmouse kernel module loaded successfully:

```bash
# Check if the module is loaded
lsmod | grep yeetmouse

# View module information
modinfo yeetmouse

# Check module parameters
ls -l /sys/module/yeetmouse/parameters/
```

If the module is not loaded, you may need to reboot or manually load it:

```bash
sudo modprobe yeetmouse
```

**2. Launch the GUI**

The YeetMouse GUI requires root privileges to modify kernel module parameters. Run it with sudo:

```bash
# Launch the GUI with sudo
sudo -E yeetmouse-gui
```

The `-E` flag preserves your environment variables, ensuring the GUI displays correctly on your desktop.

**3. Configure Mouse Acceleration**

Use the GUI to adjust acceleration curves, sensitivity, and other parameters. Changes take effect immediately.

For detailed usage instructions, see the [upstream YeetMouse documentation](https://github.com/AndyFilter/YeetMouse#readme).

## Troubleshooting

Having issues? Check out the [Troubleshooting Guide](TROUBLESHOOTING.md) for solutions to common problems including:

- Kernel module not loading
- GUI permission issues
- Package installation failures
- Kernel update issues

For additional help, see the [upstream YeetMouse issues](https://github.com/AndyFilter/YeetMouse/issues) or [open an issue](https://github.com/abirkel/yeetmouse-rpm/issues) in this repository.

## Automated Builds

This repository automatically builds and publishes RPM packages when new YeetMouse commits are detected. Packages are built daily and deployed to the GitHub Pages repository.

For detailed information about the build workflow architecture, manual build options, and configuration, see the [Workflows Guide](WORKFLOWS.md).

## Building Locally

Want to build the packages yourself or modify them? See the [Building Guide](BUILDING.md) for detailed instructions on local development.

## Contributing

This is a personal packaging project for YeetMouse. Issues and pull requests are welcome.

## License

The packaging scripts and spec files in this repository are provided as-is. The YeetMouse software itself is licensed under GPL-3.0. See the [upstream repository](https://github.com/AndyFilter/YeetMouse) for details.

## Upstream

- YeetMouse Repository: https://github.com/AndyFilter/YeetMouse
- YeetMouse Documentation: https://github.com/AndyFilter/YeetMouse#readme
