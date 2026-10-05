# Building Locally

This guide covers how to build the YeetMouse RPM packages locally on your system.

## Container Requirements (COPR)

Builds run in COPR's `fedora-44-x86_64` chroot, which provisions `kmodtool` and `kernel-devel` automatically. `kmodtool` resolves kernel-devel's installed version at spec-parse time via `rpm -q`, so no manual kernel-devel pre-install step or container selection is needed the way the old GitHub Actions pipeline required.
- `quay.io/fedora/fedora:latest` - Standard Fedora
- `fedora:43` - Specific Fedora version

### Configuration

The container image is configured in `build.conf` at the repository root:

```bash
CONTAINER_IMAGE=ghcr.io/ublue-os/aurora
CONTAINER_VERSION=latest
DEFAULT_KERNEL_TYPE=main
```

**Configuration Options**:
- `CONTAINER_IMAGE`: Default container image for builds
- `CONTAINER_VERSION`: Container image tag/version
- `DEFAULT_KERNEL_TYPE`: Default kernel type (main or bazzite)

## Prerequisites

Install the required build dependencies:

```bash
# Install build dependencies
sudo dnf install rpm-build rpmdevtools rpmlint akmods kmodtool \
                 kernel-devel gcc gcc-c++ make git wget \
                 glfw-devel mesa-libGL-devel
```

## Build Process

Follow these steps to build the packages locally:

```bash
# Clone this repository
git clone https://github.com/abirkel/yeetmouse-rpm.git
cd yeetmouse-rpm

# Set up RPM build tree
rpmdev-setuptree

# Copy spec files
cp specs/*.spec ~/rpmbuild/SPECS/
cd ~/rpmbuild/SPECS

# Set version variables
YEETMOUSE_COMMIT="99844bbd786d612657d892cac2f663d940fd3d62"  # Full commit hash
KERNEL_VERSION=$(uname -r)
RELEASE_NUMBER="1"

# Download the YeetMouse source
spectool -g -R kmod-yeetmouse.spec
spectool -g -R yeetmouse.spec

# Build the kmod package
rpmbuild --define "kernel_version ${KERNEL_VERSION}" \
         --define "commit ${YEETMOUSE_COMMIT}" \
         --define "release ${RELEASE_NUMBER}" \
         -ba kmod-yeetmouse.spec

# Build the CLI package
rpmbuild --define "commit ${YEETMOUSE_COMMIT}" \
         --define "release ${RELEASE_NUMBER}" \
         -ba yeetmouse.spec

# Find built packages
ls -l ~/rpmbuild/RPMS/x86_64/
ls -l ~/rpmbuild/SRPMS/
```

**Note**: The spec files use RPM macros for version and release numbers. You must pass these values via `--define` parameters to rpmbuild.

### Building for Different Kernel Versions

To build kmod packages for a specific kernel version:

```bash
# Install kernel-devel for target kernel
sudo dnf install kernel-devel-6.17.8-300.fc43.x86_64

# Set the kernel version
KERNEL_VERSION="6.17.8-300.fc43.x86_64"
YEETMOUSE_COMMIT="99844bbd786d612657d892cac2f663d940fd3d62"
RELEASE_NUMBER="1"

# Build kmod for that kernel
rpmbuild --define "kernel_version ${KERNEL_VERSION}" \
         --define "commit ${YEETMOUSE_COMMIT}" \
         --define "release ${RELEASE_NUMBER}" \
         -ba ~/rpmbuild/SPECS/kmod-yeetmouse.spec

# Find built kmod packages
ls -l ~/rpmbuild/RPMS/x86_64/kmod-yeetmouse*
```

**Package Naming**: The kmod package will be named `kmod-yeetmouse-{version}-{release}.{kernel_version}.rpm`, ensuring it's specific to that kernel version.

## Installing Local Builds

Once the packages are built, you can install them:

```bash
# Install the locally built packages
sudo dnf install ~/rpmbuild/RPMS/x86_64/kmod-yeetmouse-*.rpm
sudo dnf install ~/rpmbuild/RPMS/x86_64/yeetmouse-*.rpm
```

## Modifying the Spec Files

The spec files are located in the `specs/` directory:

- `specs/kmod-yeetmouse.spec` - Kernel module package
- `specs/yeetmouse.spec` - CLI tool package

The spec files use RPM macros for version and release numbers:
```spec
Version:        %{?version}%{!?version:0.9.2}
Release:        %{?release}%{!?release:1}%{?dist}
```

After making changes to the spec files, copy them to your RPM build tree and rebuild with appropriate macros:

```bash
cp specs/*.spec ~/rpmbuild/SPECS/
cd ~/rpmbuild/SPECS

# Build with version/release macros
rpmbuild --define "commit 99844bbd786d612657d892cac2f663d940fd3d62" \
         --define "release 1" \
         --define "kernel_version $(uname -r)" \
         -ba kmod-yeetmouse.spec

rpmbuild --define "commit 99844bbd786d612657d892cac2f663d940fd3d62" \
         --define "release 1" \
         -ba yeetmouse.spec
```

## Linting

Before committing changes, lint the spec files:

```bash
rpmlint specs/*.spec
```

## Troubleshooting

### Build Failures

**Missing kernel-devel**
```bash
# Install kernel-devel for your kernel
sudo dnf install kernel-devel-$(uname -r)

# Or for a specific kernel version
sudo dnf install kernel-devel-6.17.8-300.fc43.x86_64

# Check available kernel-devel versions
dnf list available kernel-devel
```

**RPM macro errors**
```bash
# Ensure you're passing all required macros
rpmbuild --define "kernel_version $(uname -r)" \
         --define "commit 99844bbd786d612657d892cac2f663d940fd3d62" \
         --define "release 1" \
         -ba kmod-yeetmouse.spec

# Check spec file for required macros
grep -E "%(version|release|kernel_version|commit)" specs/kmod-yeetmouse.spec
```

**Compilation errors**
```bash
# Check build logs
less ~/rpmbuild/BUILD/yeetmouse-*/build.log

# Verify kernel-devel matches your kernel
rpm -q kernel-devel

# Ensure build dependencies are installed
sudo dnf builddep specs/kmod-yeetmouse.spec
```

**Module fails to load after installation**
```bash
# Check if module was built
ls -la /lib/modules/$(uname -r)/extra/yeetmouse/

# Try loading manually with verbose output
sudo modprobe -v yeetmouse

# Check kernel logs for errors
sudo dmesg | grep yeetmouse

# Verify module signature (if secure boot enabled)
modinfo yeetmouse | grep signature
```

### Version Mismatch Issues

**kmod package doesn't match running kernel**
```bash
# Check your kernel version
uname -r

# Build kmod for your specific kernel
KERNEL_VERSION=$(uname -r)
rpmbuild --define "kernel_version ${KERNEL_VERSION}" \
         --define "commit 99844bbd786d612657d892cac2f663d940fd3d62" \
         --define "release 1" \
         -ba kmod-yeetmouse.spec

# Install the matching package
sudo dnf install ~/rpmbuild/RPMS/x86_64/kmod-yeetmouse-*$(uname -r)*.rpm
```

## Package Signing

COPR signs published packages with its own per-project GPG key; there are no repository secrets to configure. The signing key is published automatically alongside the repository and imported on first install.

### Verifying Signed Packages

Users can verify the authenticity of published packages using:

```bash
# Import the public key
rpm --import https://raw.githubusercontent.com/<owner>/<repo>/main/RPM-GPG-KEY-yeetmouse

# Verify a package
rpm -K ~/rpmbuild/RPMS/x86_64/yeetmouse-*.rpm
```
