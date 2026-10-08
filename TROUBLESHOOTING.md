# Troubleshooting Guide

This guide covers common issues you may encounter when installing or using YeetMouse RPM packages.

Three packages are published: `kmod-yeetmouse` (the kernel module, built per-kernel-version
via COPR/kmodtool), `yeetmouse` (the `yeetmousectl` CLI and the systemd service that applies
`/etc/yeetmouse.conf` at boot), and `yeetmouse-gui` (the graphical configuration tool). There
is no `akmod-yeetmouse` package -- akmod support was deliberately removed from this project in
favor of prebuilt COPR kmod packages, since the target systems (Fedora Atomic/rpm-ostree) have
no local compiler toolchain for akmod to build against.

## Kernel Module Not Loading

**Problem**: The yeetmouse module doesn't appear in `lsmod` output.

**Solutions**:
```bash
# Confirm the kmod package for your exact running kernel is installed
rpm -qa | grep kmod-yeetmouse
uname -r

# Manually load the module
sudo modprobe yeetmouse

# Verify the module file exists for your kernel version
ls -l /lib/modules/$(uname -r)/extra/yeetmouse.ko*

# Check dmesg for module load errors
sudo dmesg | grep -i yeetmouse
```

**Common Causes**:
- No `kmod-yeetmouse` build exists yet for your exact kernel version (check the repo for a
  newer package, or wait for the next automated rebuild)
- Secure Boot is enabled (unsigned modules cannot load, see the Secure Boot section below)
- The `yeetmouse-kmod-common` metadata package is missing (required alongside the per-kernel
  subpackage; `sudo dnf install yeetmouse-kmod-common` if `dnf` reports a missing dependency)

## GUI Permission Issues

**Problem**: GUI fails to start or cannot modify kernel module parameters.

**Solutions**:
```bash
# Always run the GUI with sudo
sudo -E yeetmouse-gui

# The -E flag preserves your environment variables for proper display

# If display issues occur, try
sudo env DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY yeetmouse-gui

# Check that the kernel module is loaded first
lsmod | grep yeetmouse

# Verify module parameters are accessible
ls -l /sys/module/yeetmouse/parameters/
```

**Why sudo is required**: The YeetMouse GUI needs root privileges to write to kernel module
parameters in `/sys/module/yeetmouse/parameters/`. Saving a config persistently also shells
out to `yeetmousectl` via `pkexec` (see the `yeetmouse` package's `yeetmousectl`), so that
package must be installed alongside `yeetmouse-gui`.

## Package Installation Fails

**Problem**: DNF cannot find the yeetmouse package or GPG verification fails.

**Solutions**:
```bash
# Verify repository is configured
cat /etc/yum.repos.d/abirkel-stable.repo

# Check repository is enabled
sudo dnf repolist | grep yeetmouse

# Clear DNF cache and retry
sudo dnf clean all
sudo dnf makecache

# If GPG verification fails, manually import the key
sudo rpm --import https://raw.githubusercontent.com/abirkel/yeetmouse-rpm/main/RPM-GPG-KEY-yeetmouse

# Try installing again
sudo dnf install kmod-yeetmouse yeetmouse yeetmouse-gui
```

## Kernel Update Breaks Module

**Problem**: After a kernel update, yeetmouse stops working.

**Solutions**:
```bash
# Check if a kmod package exists for your new kernel
dnf list available | grep kmod-yeetmouse

# If available, update to it
sudo dnf update kmod-yeetmouse

# If not available yet, check back after the next scheduled rebuild, or trigger one
# via the repo's own kernel-bump poller if you maintain this repo yourself
```

## GUI Display Issues

**Problem**: GUI window doesn't appear or displays incorrectly.

**Solutions**:
```bash
# Ensure X11 or Wayland session is running
echo $DISPLAY
echo $WAYLAND_DISPLAY

# Run with environment preservation
sudo -E yeetmouse-gui

# For Wayland, you may need
sudo env WAYLAND_DISPLAY=$WAYLAND_DISPLAY yeetmouse-gui

# Check GUI dependencies are installed
rpm -q yeetmouse-gui glfw mesa-libGL

# Verify the GUI binary exists
which yeetmouse-gui
ls -l /usr/bin/yeetmouse-gui
```

## Module Parameters Not Changing

**Problem**: Changes in the GUI don't affect mouse behavior.

**Solutions**:
```bash
# Verify the module is loaded
lsmod | grep yeetmouse

# Check current parameter values
cat /sys/module/yeetmouse/parameters/*

# Try manually setting a parameter to test
echo 1 | sudo tee /sys/module/yeetmouse/parameters/enabled

# Reload the module
sudo modprobe -r yeetmouse
sudo modprobe yeetmouse

# Check dmesg for module messages
sudo dmesg | grep -i yeetmouse
```

## Secure Boot Issues

**Problem**: Module fails to load with "Operation not permitted" on systems with Secure Boot.

**Solutions**:

**Option 1: Disable Secure Boot** (easiest)
- Reboot into BIOS/UEFI settings
- Disable Secure Boot
- Save and reboot

**Option 2: Sign the module** (advanced)
```bash
# Generate a Machine Owner Key (MOK)
sudo mokutil --generate-key

# Enroll the key (requires reboot and BIOS password entry)
sudo mokutil --import MOK.der

# Sign the module
sudo /usr/src/kernels/$(uname -r)/scripts/sign-file \
  sha256 MOK.priv MOK.der \
  /lib/modules/$(uname -r)/extra/yeetmouse.ko
```

## Checking Build Status

Packages are built on [COPR](https://copr.fedorainfracloud.org/coprs/abirkel/yeetmouse/), not
GitHub Actions. To check build status:

1. Visit the project's COPR page and open the Builds tab
2. Check the latest build's status for each of the three packages
   (`kmod-yeetmouse`, `yeetmouse`, `yeetmouse-gui`)
3. Click into a build to view its SRPM and per-chroot build logs if something failed

## Package Version Mismatch

**Problem**: Installed packages show different versions or commits.

**Solutions**:
```bash
# Check installed package versions
rpm -qa | grep yeetmouse

# Update all yeetmouse packages together
sudo dnf update kmod-yeetmouse yeetmouse yeetmouse-gui

# Or reinstall to ensure consistency
sudo dnf reinstall kmod-yeetmouse yeetmouse yeetmouse-gui
```

## Uninstalling YeetMouse

If you need to completely remove YeetMouse:

```bash
# Unload the kernel module
sudo modprobe -r yeetmouse

# Remove packages
sudo dnf remove kmod-yeetmouse yeetmouse-kmod-common yeetmouse yeetmouse-gui

# Remove repository configuration (optional)
sudo rm /etc/yum.repos.d/abirkel-stable.repo
```

## Reporting Issues

If you encounter problems not covered here:

1. **Check upstream issues**: Many issues may be related to YeetMouse itself, not the packaging. See [YeetMouse issues](https://github.com/AndyFilter/YeetMouse/issues)
2. **Check package issues**: For packaging-specific problems, check [this repository's issues](https://github.com/abirkel/yeetmouse-rpm/issues)
3. **Create a new issue**: Include:
   - Your Fedora version (`cat /etc/fedora-release`)
   - Kernel version (`uname -r`)
   - Package versions (`rpm -qa | grep yeetmouse`)
   - Relevant log output (`sudo dmesg | grep -i yeetmouse`)
   - Steps to reproduce the problem

## Additional Resources

- [YeetMouse Documentation](https://github.com/AndyFilter/YeetMouse#readme)
- [Building Guide](BUILDING.md) - For local development and testing
