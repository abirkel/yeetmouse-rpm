# Build Workflows

This repository uses automated GitHub Actions workflows to build and publish RPM packages.

## Workflow Architecture

The build workflow consists of five jobs that run in sequence:

1. **load-config**: Loads build configuration from `build.conf`
2. **update-specs** (optional): Updates spec files with new commit hash, version, and release numbers, then commits changes
3. **build-rpm**: Builds RPM packages in a container with the specified kernel-devel
4. **publish**: Creates GitHub release and deploys packages to GitHub Pages repository
5. **cleanup-on-failure** (conditional): Reverts spec updates if build or publish fails

**Key Features:**
- Spec files are the single source of truth for package versions and commit hashes
- Version updates are committed before building to maintain consistency
- Automatic rollback of spec changes if builds fail
- Supports building against specific container images with matching kernel-devel packages
- Tracks YeetMouse by git commit hash instead of version tags

## Automatic Builds

### YeetMouse Commit Detection (`check-release.yml`)

- Runs daily to check for new YeetMouse commits on the main branch
- Automatically triggers a full build (akmod + kmod + GUI) when a new commit is detected
- Extracts DKMS_VER from the commit's Makefile to determine the package version
- Uses `update_specs: true` to update spec files with the new commit hash and version

### Container Image Monitoring

- Monitors the container image specified in `build.conf`
- Detects kernel version changes in the image
- Automatically triggers kmod-only rebuilds when the kernel updates
- Supports multiple registries: GitHub Container Registry (ghcr.io), Quay.io, and Docker Hub

## Manual Builds

Trigger builds manually via GitHub Actions with custom options:

**Build Current Commit** (uses commit from spec files)
```bash
gh workflow run build-rpm.yml
```

**Update to New Commit and Build**
```bash
gh workflow run build-rpm.yml \
  -f yeetmouse_commit=99844bbd786d612657d892cac2f663d940fd3d62 \
  -f update_specs=true
```

**Rebuild Same Commit** (increments release number)
```bash
gh workflow run build-rpm.yml \
  -f yeetmouse_commit=99844bbd786d612657d892cac2f663d940fd3d62 \
  -f update_specs=true
```

**Kmod Only** (for kernel updates)
```bash
gh workflow run build-rpm.yml \
  -f build_akmod=false \
  -f build_cli=false \
  -f build_kmod=true
```

**Akmod + GUI Only** (no kmod)
```bash
gh workflow run build-rpm.yml \
  -f build_akmod=true \
  -f build_cli=true \
  -f build_kmod=false
```

**Custom Container Image**
```bash
gh workflow run build-rpm.yml \
  -f container_image=quay.io/ublue/aurora \
  -f fedora_version=40
```

## Build Configuration

Edit `build.conf` to customize the default container image:

```bash
CONTAINER_IMAGE=ghcr.io/ublue-os/aurora-nvidia-open
CONTAINER_VERSION=latest
ENABLE_KMOD=true
```

### Container Requirements

This workflow is designed to build kmod packages for uBlue atomic images. uBlue images often ship with kernels slightly behind Fedora main, and the corresponding kernel-devel packages are no longer available in standard repositories—they only exist in the images themselves.

- **For kmod builds**: Requires a full OS container with kernel-devel installed (e.g., Aurora)
- **For akmod + GUI only**: Can use smaller Fedora images (e.g., `fedora:latest`)
- **To disable kmod**: Set `ENABLE_KMOD=false` in `build.conf`

See [Building Guide](BUILDING.md) for detailed container selection guidance.

## Build Inputs

The `build-rpm.yml` workflow accepts these inputs:

- `yeetmouse_commit` (string, optional) - YeetMouse commit hash to build (full 40-character hash). Only used with `update_specs`
- `update_specs` (boolean, default: false) - Update spec files with new commit hash, version, and release numbers before building
- `build_akmod` (boolean, default: true) - Build akmod package
- `build_cli` (boolean, default: true) - Build GUI package (yeetmouse-gui)
- `build_kmod` (boolean, default: false) - Build kmod package
- `container_image` (string, optional) - Container image to use (overrides build.conf default)
- `fedora_version` (string, optional) - Container version tag (overrides build.conf default)

### Important Notes

- The commit hash that gets built is determined by the `%global commit` variable in the spec files
- The version is extracted from the DKMS_VER in the Makefile of the commit being built
- Use `update_specs: true` with `yeetmouse_commit` to update specs to a new commit before building
- Without `update_specs`, the workflow builds whatever commit is currently in the spec files
- Spec files are the single source of truth for package commits and versions

### Version Update Behavior

When `update_specs: true` is used:

- **New DKMS_VER**: Updates `Version:` to new value, resets `Release:` to 1.git{shortcommit}, adds changelog entry
- **Same DKMS_VER, new commit**: Keeps `Version:` unchanged, resets `Release:` to 1.git{shortcommit}, adds commit update changelog entry
- **Same DKMS_VER and commit**: Keeps `Version:` unchanged, increments `Release:` number before .git{shortcommit}, adds rebuild changelog entry
- **Automatic rollback**: If build fails after updating specs, the commit is automatically reverted

### Commit-Based Versioning

YeetMouse uses git commits instead of version tags:

- **Commit tracking**: The `%global commit` variable stores the full 40-character commit hash
- **Short commit**: The `%global shortcommit` variable stores the first 7 characters for display
- **Release format**: Release numbers include the short commit: `1.git99844bb%{?dist}`
- **Source URL**: Downloads from GitHub archive: `/archive/{commit}/YeetMouse-{commit}.tar.gz`
- **Version extraction**: DKMS_VER is extracted from the Makefile of the commit being built

This approach ensures reproducible builds tied to specific YeetMouse source code states.

## Workflow Outputs

The workflows produce several outputs:

### Build Artifacts

- **RPM packages**: Signed packages for akmod, kmod, and GUI
- **Build logs**: Detailed logs from rpmbuild for each package
- **Spec files**: Updated spec files used for the build
- **Build metadata**: JSON file with commit hash, kernel version, and container image info

### GitHub Release

- **Tag format**: `build-v{version}-{shortcommit}` (e.g., `build-v0.9.2-99844bb`)
- **Release notes**: Include build information, commit hash, kernel version, and installation instructions
- **Assets**: All signed RPM packages attached to the release

### GitHub Pages Repository

- **Package repository**: All packages merged into a single DNF/YUM repository
- **Metadata**: createrepo_c metadata for package management
- **URL**: `https://<owner>.github.io/<repo>`
- **GPG verification**: Packages signed with repository GPG key

## Troubleshooting Workflows

### Build Failures

If a build fails:

1. Check the workflow run logs in GitHub Actions
2. Look for rpmbuild errors in the build-rpm job
3. Verify BuildRequires are satisfied in the container
4. Check that the commit hash is valid and accessible

If `update_specs` was used, the spec update commit will be automatically reverted.

### Source Download Failures

If spectool cannot download sources:

1. Verify the commit hash exists in the YeetMouse repository
2. Check that GitHub is accessible from the workflow runner
3. Verify the Source0 URL format in spec files matches: `/archive/{commit}/YeetMouse-{commit}.tar.gz`

### Container Issues

If the container cannot be pulled or doesn't have required packages:

1. Verify the container image exists and is accessible
2. For kmod builds, ensure the image has kernel-devel installed
3. Check `build.conf` for correct image name and version
4. Consider using a different container image via workflow inputs

### Spec Update Rollback

The cleanup-on-failure job automatically reverts spec updates if builds fail:

1. Only runs if update-specs succeeded but build-rpm or publish failed
2. Uses `git revert` to undo the spec update commit
3. Pushes the revert commit to keep the repository in a clean state
4. Check the workflow logs to see the revert operation

## Advanced Usage

### Building for Multiple Kernels

To build kmod packages for different kernel versions:

```bash
# Build for Aurora kernel
gh workflow run build-rpm.yml \
  -f build_akmod=false \
  -f build_cli=false \
  -f build_kmod=true \
  -f container_image=ghcr.io/ublue-os/aurora-nvidia-open \
  -f fedora_version=latest

# Build for Bazzite kernel
gh workflow run build-rpm.yml \
  -f build_akmod=false \
  -f build_cli=false \
  -f build_kmod=true \
  -f container_image=ghcr.io/ublue-os/bazzite \
  -f fedora_version=stable
```

### Testing Unreleased Commits

To test a specific YeetMouse commit before it's automatically detected:

```bash
gh workflow run build-rpm.yml \
  -f yeetmouse_commit=<full-commit-hash> \
  -f update_specs=true
```

This updates the spec files to the specified commit and builds packages for testing.
