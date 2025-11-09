# Building Locally

This guide covers how to build the YeetMouse RPM packages locally on your system.

## Container Requirements (GitHub Actions)

The automated build workflows use containers to ensure consistent builds. **Important**: kmod builds require a full OS container with kernel development tools installed.

### Why Full OS Images are Required for kmod

This workflow is designed to build kmod packages for uBlue atomic images against the kernel-devel packages installed in those images. uBlue images often ship with kernels slightly behind Fedora main, and the corresponding kernel-devel packages are no longer available in the standard Fedora repositories. The only way to get these older kernel-devel packages is from the images themselves.

**Current Limitation**: The workflow does not yet support building kmod against the latest Fedora kernel from repositories. It only builds against the kernel-devel found in the container image.

### Container Image Selection

**For kmod builds** (building pre-compiled kernel modules):
- **Required**: Full OS container with kernel-devel installed
- **Recommended**: `ghcr.io/ublue-os/aurora-nvidia-open` (uBlue Aurora with kernel-devel)
- **Why**: Contains the kernel-devel package matching the image's kernel version
- **Not suitable**: Minimal containers like `fedora:minimal` (missing kernel-devel)

**For akmod + GUI only** (no kmod):
- **Flexible**: Can use smaller Fedora tooling images
- **Example**: `fedora:latest` or `fedora:40`
- **Benefit**: Faster builds, smaller image size
- **Note**: akmod packages are kernel-agnostic and rebuild on user systems

### Configuration

The container image is configured in `build.conf` at the repository root:

```bash
# For kmod builds (requires full OS with kernel-devel)
CONTAINER_IMAGE=ghcr.io/ublue-os/aurora-nvidia-open
CONTAINER_VERSION=latest
ENABLE_KMOD=true

# For akmod + GUI only (can use minimal image)
# CONTAINER_IMAGE=fedora
# CONTAINER_VERSION=latest
# ENABLE_KMOD=false
```

To disable kmod builds entirely and use a smaller image, set `ENABLE_KMOD=false`.

## Prerequisites

Install the required build dependencies:

```bash
# Install build dependencies
sudo dnf install rpm-build rpmdevtools rpmlint akmods kmodtool \
                 kernel-devel gcc gcc-c++ make git wget \
                 glfw-devel mesa-libGL-devel
```

## Build Process

Follow these steps to build the packages:

```bash
# Clone this repository
git clone https://github.com/abirkel/yeetmouse-rpm.git
cd yeetmouse-rpm

# Set up RPM build tree
rpmdev-setuptree

# Copy spec files to see what version they specify
cp specs/*.spec ~/rpmbuild/SPECS/
cd ~/rpmbuild/SPECS

# Check the version and commit in the spec file
grep "^%global commit" akmod-yeetmouse.spec
grep "^Version:" akmod-yeetmouse.spec

# Download the YeetMouse source (spectool reads from spec file)
spectool -g -R akmod-yeetmouse.spec
spectool -g -R kmod-yeetmouse.spec
spectool -g -R yeetmouse-gui.spec

# Build the packages
rpmbuild -ba akmod-yeetmouse.spec
rpmbuild -ba kmod-yeetmouse.spec
rpmbuild -ba yeetmouse-gui.spec

# Find built packages
ls -l ~/rpmbuild/RPMS/x86_64/
ls -l ~/rpmbuild/SRPMS/
```

**Note**: The spec files contain the commit hash and version to build. To build a different commit, edit the `%global commit` and `Version:` fields in the spec files before running spectool and rpmbuild.

## Installing Local Builds

Once the packages are built, you can install them:

```bash
# Install the locally built packages
sudo dnf install ~/rpmbuild/RPMS/x86_64/akmod-yeetmouse-*.rpm
sudo dnf install ~/rpmbuild/RPMS/x86_64/yeetmouse-gui-*.rpm

# Or install kmod instead of akmod
sudo dnf install ~/rpmbuild/RPMS/x86_64/kmod-yeetmouse-*.rpm
sudo dnf install ~/rpmbuild/RPMS/x86_64/yeetmouse-gui-*.rpm
```

## Modifying the Spec Files

The spec files are located in the `specs/` directory:

- `specs/akmod-yeetmouse.spec` - Automatic kernel module package
- `specs/kmod-yeetmouse.spec` - Pre-compiled kernel module package
- `specs/yeetmouse-gui.spec` - GUI application package

### Updating to a New Commit

To build a different YeetMouse commit:

1. Find the commit hash you want to build from the [YeetMouse repository](https://github.com/AndyFilter/YeetMouse)
2. Extract the DKMS_VER from that commit's Makefile
3. Update all three spec files:

```bash
# Example: Update to commit 99844bbd786d612657d892cac2f663d940fd3d62
NEW_COMMIT="99844bbd786d612657d892cac2f663d940fd3d62"
SHORT_COMMIT="${NEW_COMMIT:0:7}"

# Extract DKMS_VER from the commit
curl -sL "https://raw.githubusercontent.com/AndyFilter/YeetMouse/${NEW_COMMIT}/Makefile" | \
  grep "^DKMS_VER" | cut -d'=' -f2 | xargs

# Update spec files
sed -i "s/^%global commit.*/%global commit ${NEW_COMMIT}/" specs/*.spec
sed -i "s/^%global shortcommit.*/%global shortcommit ${SHORT_COMMIT}/" specs/*.spec
sed -i "s/^Version:.*/Version:        <DKMS_VER>/" specs/*.spec
sed -i "s/^Release:.*/Release:        1.git%{shortcommit}%{?dist}/" specs/*.spec
```

After making changes to the spec files, copy them to your RPM build tree and rebuild:

```bash
cp specs/*.spec ~/rpmbuild/SPECS/
cd ~/rpmbuild/SPECS
rpmbuild -ba akmod-yeetmouse.spec
rpmbuild -ba kmod-yeetmouse.spec
rpmbuild -ba yeetmouse-gui.spec
```

## Linting

Before committing changes, lint the spec files:

```bash
rpmlint specs/*.spec
```

Address any errors reported by rpmlint. Some warnings may be acceptable depending on context.

## GitHub Actions Secrets

The automated build workflow requires the following secrets to be configured in your GitHub repository settings:

### Required Secrets

- **`GPG_PRIVATE_KEY`**: Base64-encoded GPG private key for signing RPM packages
  - Generate with: `gpg --export-secret-key --armor <KEY_ID> | base64 -w0`
  - Store the base64 output as this secret

- **`GPG_PASSPHRASE`**: Passphrase for the GPG private key

- **`GPG_KEY_ID`**: The GPG key ID used for signing (e.g., `1234567890ABCDEF`)

### Generating GPG Keys

If you don't have a GPG key yet:

```bash
# Generate a new GPG key
gpg --full-generate-key

# List your keys to find the key ID
gpg --list-secret-keys --keyid-format=long

# Export the public key to the repository
gpg --armor --export <KEY_ID> > RPM-GPG-KEY-yeetmouse

# Export the private key as base64 for GitHub secrets
gpg --export-secret-key --armor <KEY_ID> | base64 -w0
```

### Setting Up Secrets

1. Go to your repository on GitHub
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret with the name and value listed above

### Verifying Signed Packages

Users can verify the authenticity of published packages using:

```bash
# Import the public key
rpm --import https://raw.githubusercontent.com/<owner>/<repo>/main/RPM-GPG-KEY-yeetmouse

# Verify a package
rpm -K ~/rpmbuild/RPMS/x86_64/yeetmouse-gui-*.rpm
```

## Troubleshooting Local Builds

### Missing Dependencies

If rpmbuild fails with missing dependencies:

```bash
# Install BuildRequires from spec files
sudo dnf builddep specs/akmod-yeetmouse.spec
sudo dnf builddep specs/kmod-yeetmouse.spec
sudo dnf builddep specs/yeetmouse-gui.spec
```

### Source Download Failures

If spectool cannot download the source:

1. Verify the commit hash exists in the YeetMouse repository
2. Check your internet connection
3. Manually download the source:

```bash
COMMIT="99844bbd786d612657d892cac2f663d940fd3d62"
wget "https://github.com/AndyFilter/YeetMouse/archive/${COMMIT}/YeetMouse-${COMMIT}.tar.gz" \
  -O ~/rpmbuild/SOURCES/YeetMouse-${COMMIT}.tar.gz
```

### kmod Build Failures

If kmod builds fail with "kernel-devel not found":

1. Ensure kernel-devel is installed: `sudo dnf install kernel-devel`
2. Verify it matches your running kernel: `uname -r`
3. If building for a different kernel, install the matching kernel-devel package
