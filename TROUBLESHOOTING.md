# Troubleshooting Guide

This guide covers common issues you may encounter when installing or using YeetMouse RPM packages.

## Kernel Module Not Loading

**Problem**: The yeetmouse module doesn't appear in `lsmod` output.

**Solutions**:
```bash
# Check if akmod build completed successfully
sudo akmods --force --kernel $(uname -r)

# Check akmod logs
sudo journalctl -u akmods

# Manually load the module
sudo modprobe yeetmouse

# Check for build errors
ls -l /usr/src/akmods/yeetmouse-kmod-*/

# Verify the module file exists
ls -l /lib/modules/$(uname -r)/extra/yeetmouse.ko*
```

**Common Causes**:
- Akmod build failed due to missing kernel-devel
- Secure Boot is enabled (unsigned modules cannot load)
- Module build is still in progress (wait a few minutes after installation)

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

**Why sudo is required**: The YeetMouse GUI needs root privileges to write to kernel module parameters in `/sys/module/yeetmouse/parameters/`.

## Package Installation Fails

**Problem**: DNF cannot find the yeetmouse package or GPG verification fails.

**Solutions**:
```bash
# Verify repository is configured
cat /etc/yum.repos.d/yeetmouse.repo

# Check repository is enabled
sudo dnf repolist | grep yeetmouse

# Clear DNF cache and retry
sudo dnf clean all
sudo dnf makecache

# If GPG verification fails, manually import the key
sudo rpm --import https://raw.githubusercontent.com/abirkel/yeetmouse-rpm/main/RPM-GPG-KEY-yeetmouse

# Try installing again
sudo dnf install akmod-yeetmouse yeetmouse-gui
```

## Kernel Update Breaks Module

**Problem**: After a kernel update, yeetmouse stops working.

**Solutions**:

**If using akmod** (recommended):
```bash
# The akmod should rebuild automatically, but you can force it
sudo akmods --force --kernel $(uname -r)

# Check if the module exists for your kernel
ls -l /lib/modules/$(uname -r)/extra/yeetmouse.ko*

# Reboot if necessary
sudo reboot
```

**If using kmod**:
```bash
# Check if a kmod package exists for your new kernel
dnf list available | grep kmod-yeetmouse

# If available, update to the new kmod
sudo dnf update kmod-yeetmouse

# If not available, switch to akmod
sudo dnf remove kmod-yeetmouse
sudo dnf install akmod-yeetmouse
```

## Akmod Build Failures

**Problem**: Akmod fails to build the kernel module.

**Solutions**:
```bash
# Install kernel-devel for your kernel
sudo dnf install kernel-devel-$(uname -r)

# If kernel-devel is not available, update your kernel
sudo dnf update kernel kernel-devel

# Force akmod rebuild
sudo akmods --force --kernel $(uname -r)

# Check build logs for errors
sudo journalctl -u akmods -n 100

# Verify gcc and make are installed
sudo dnf install gcc make
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

To check the status of package builds in this repository:

1. Visit the [Actions tab](https://github.com/abirkel/yeetmouse-rpm/actions) on GitHub
2. Look for the latest "Build and Publish RPM Packages" workflow run
3. Check the workflow logs for any build errors
4. Verify the latest release in the [Releases section](https://github.com/abirkel/yeetmouse-rpm/releases)

## Package Version Mismatch

**Problem**: Installed packages show different versions or commits.

**Solutions**:
```bash
# Check installed package versions
rpm -qa | grep yeetmouse

# Update all yeetmouse packages together
sudo dnf update akmod-yeetmouse yeetmouse-gui

# Or reinstall to ensure consistency
sudo dnf reinstall akmod-yeetmouse yeetmouse-gui
```

## Uninstalling YeetMouse

If you need to completely remove YeetMouse:

```bash
# Unload the kernel module
sudo modprobe -r yeetmouse

# Remove packages
sudo dnf remove akmod-yeetmouse kmod-yeetmouse yeetmouse-gui

# Remove repository configuration (optional)
sudo rm /etc/yum.repos.d/yeetmouse.repo

# Clean up any remaining files
sudo rm -rf /usr/src/akmods/yeetmouse-kmod-*
```

## Reporting Issues

If you encounter problems not covered here:

1. **Check upstream issues**: Many issues may be related to YeetMouse itself, not the packaging. See [YeetMouse issues](https://github.com/AndyFilter/YeetMouse/issues)
2. **Check package issues**: For packaging-specific problems, check [this repository's issues](https://github.com/abirkel/yeetmouse-rpm/issues)
3. **Create a new issue**: Include:
   - Your Fedora version (`cat /etc/fedora-release`)
   - Kernel version (`uname -r`)
   - Package versions (`rpm -qa | grep yeetmouse`)
   - Whether you're using akmod or kmod
   - Relevant log output (`sudo journalctl -u akmods`, `dmesg | grep yeetmouse`)
   - Steps to reproduce the problem

## Additional Resources

- [YeetMouse Documentation](https://github.com/AndyFilter/YeetMouse#readme)
- [Building Guide](BUILDING.md) - For local development and testing
- [Workflows Guide](WORKFLOWS.md) - For understanding the build process
