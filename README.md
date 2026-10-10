# YeetMouse RPM Packaging

[![COPR build](https://copr.fedorainfracloud.org/coprs/abirkel/yeetmouse/package/kmod-yeetmouse/status_image/last_build.png)](https://copr.fedorainfracloud.org/coprs/abirkel/yeetmouse/)
[![Platform](https://img.shields.io/badge/Platform-Fedora%20%7C%20RPM-294172?logo=fedora)](https://github.com/abirkel/yeetmouse-rpm)

RPM packages for the [YeetMouse](https://github.com/AndyFilter/YeetMouse) mouse acceleration driver for Fedora and RPM-based Linux distributions.

## Overview

This repository provides automated RPM packaging for YeetMouse, a customizable mouse acceleration driver consisting of a kernel module, a CLI tool, and a GUI configuration tool. Packages are built via [COPR](https://copr.fedorainfracloud.org/) and published to a GPG-signed repository.

## Packages

- **kmod-yeetmouse**: Pre-compiled kernel module packages for specific kernel versions.
  Automatically rebuilt when the upstream driver changes or Fedora's kernel bumps.
- **yeetmouse**: `yeetmousectl` CLI tool and the systemd service that applies
  `/etc/yeetmouse.conf` at boot
- **yeetmouse-gui**: Graphical application for configuring mouse acceleration parameters

## Installation

**Prerequisites**: Fedora or compatible RPM-based distribution (x86_64)

### Repository Setup

Enable the COPR repository:

```bash
sudo dnf copr enable abirkel/yeetmouse
```

On an rpm-ostree system (Fedora Atomic desktops), `dnf copr` is not available. Download the repo file from the [COPR project page](https://copr.fedorainfracloud.org/coprs/abirkel/yeetmouse/) into `/etc/yum.repos.d/` instead. COPR signs the packages, and the key is imported the first time you install from the repository.

### Package Installation

Install the kmod for your running kernel, the CLI and the GUI:

```bash
sudo dnf install "kmod-yeetmouse-$(uname -r)" yeetmouse yeetmouse-gui
```

On an rpm-ostree system, layer the same packages and reboot into the new deployment:

```bash
sudo rpm-ostree install "kmod-yeetmouse-$(uname -r)" yeetmouse yeetmouse-gui
systemctl reboot
```

The kmod package name includes the kernel it was built for, for example
`kmod-yeetmouse-7.2.9-200.fc44.x86_64`, so name it with `$(uname -r)` as above.
`yeetmouse-gui` requires some kmod-yeetmouse package and `yeetmouse`, but left to choose on
its own, `dnf` could pick a kmod built for a different kernel. `yeetmouse` does not require
the kmod at all. Leave out `yeetmouse-gui` if you only want the CLI and service.

The kmod is pre-compiled for each Fedora kernel, so installation needs no local compilation.

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

The `-E` flag preserves your environment variables, ensuring the GUI displays correctly on your desktop. The binary is installed as `/usr/bin/yeetmouse-gui`.

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

This repository builds and publishes RPM packages via [COPR](https://copr.fedorainfracloud.org/coprs/abirkel/yeetmouse/), using `kmodtool` to generate per-kernel-version subpackages. GitHub Actions workflows start every build through COPR's API:

- `poll-upstream-commit.yml` (every 12 hours) moves the commit pin to the latest upstream YeetMouse commit and builds all three packages.
- `poll-kernel-bump.yml` (every 12 hours) builds `kmod-yeetmouse` for a new Fedora kernel.
- `check-and-build.yml` (every push to `main`) checks that each changed package's `%global pkgserial` went up, then builds whatever is not yet published. Pull requests targeting `main` get the check only.

Each spec's `Release` is `<pkgserial>.<commit date>git<short commit>`, and `pkgserial` alone decides which build is newer. A packaging-only change to a spec, or to a file it uses, must raise that spec's `pkgserial`. Otherwise `check-and-build.yml` fails the pull request or the push to `main`.

## Building Locally

Want to build the packages yourself or modify them? See the [Building Guide](BUILDING.md) for detailed instructions on local development.

## Contributing

This is a personal packaging project for YeetMouse. Issues and pull requests are welcome.

## License

The packaging scripts and spec files in this repository are provided as-is. The YeetMouse software itself is licensed under GPL-3.0. See the [upstream repository](https://github.com/AndyFilter/YeetMouse) for details.

## Upstream

- YeetMouse Repository: https://github.com/AndyFilter/YeetMouse
- YeetMouse Documentation: https://github.com/AndyFilter/YeetMouse#readme
