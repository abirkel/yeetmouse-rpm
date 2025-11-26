# Build Workflows

This repository uses automated GitHub Actions workflows to build and publish RPM packages for multiple kernel types.

## Workflow Architecture

The build workflow uses a matrix strategy to build packages for different kernel types in parallel:

1. **load-config**: Loads build configuration from `build.conf`
2. **generate-matrix**: Creates build matrix based on kernel types to build
3. **resolve-versions**: Determines kernel versions for each kernel type
4. **build-rpm** (matrix): Builds RPM packages in parallel for each kernel type
5. **publish**: Collects all artifacts, signs packages, and deploys to GitHub release and Pages

**Key Features:**
- Matrix builds for multiple kernel types (main and bazzite)
- Automatic kernel version detection from distribution images
- Dynamic release number management
- Spec files use RPM macros for version/release (never modified)
- Parallel builds for faster execution
- Atomic publishing of all packages together

## Automatic Builds

### Version Monitoring (`check-release.yml`)

The workflow monitors three version sources daily:

1. **YeetMouse Upstream**: Latest commit from AndyFilter/YeetMouse repository
2. **Aurora Kernel**: Kernel version from ghcr.io/ublue-os/aurora:latest (ostree.linux label)
3. **Bazzite Kernel**: Kernel version from ghcr.io/ublue-os/bazzite:latest (ostree.linux label)

**Build Trigger Logic**:
- **New YeetMouse commit**: Builds kmod for both kernel types + CLI
- **New Aurora kernel only**: Builds kmod for main kernel type only
- **New Bazzite kernel only**: Builds kmod for bazzite kernel type only
- **Multiple changes**: Triggers appropriate combination of builds

The workflow compares current versions with `.external_versions` file to detect changes.

### Version Tracking (`.external_versions`)

The `.external_versions` file tracks the last known versions to detect when new builds are needed. This file is automatically updated by the `check-release.yml` workflow.

**File Format:**
```bash
YEETMOUSE_COMMIT=99844bbd786d612657d892cac2f663d940fd3d62
AURORA_KERNEL_VERSION=6.17.8-300.fc43.x86_64
BAZZITE_KERNEL_VERSION=6.17.7-ba14.fc43.x86_64
```

**Fields:**
- `YEETMOUSE_COMMIT`: Latest YeetMouse commit hash from upstream repository
- `AURORA_KERNEL_VERSION`: Kernel version from Aurora image (ostree.linux label)
- `BAZZITE_KERNEL_VERSION`: Kernel version from Bazzite image (ostree.linux label)

**How It Works:**
1. The workflow queries current versions from upstream sources using:
   - GitHub API for YeetMouse commits
   - `skopeo inspect` for Aurora kernel version
   - `skopeo inspect` for Bazzite kernel version
2. Compares them with values in `.external_versions`
3. If any version has changed, triggers appropriate builds
4. Updates `.external_versions` with new values after triggering build

**Manual Updates:**
You can manually edit this file to force a rebuild:
```bash
# Edit the file to change a version
vim .external_versions

# Commit and push
git add .external_versions && git commit -m "chore: force rebuild for kernel update" && git push
```

This will trigger the daily check workflow to detect the change and start a build.

## Manual Builds

Trigger builds manually via GitHub Actions with custom options.

### Kernel Types

The workflow supports two kernel types:

- **main**: Standard Fedora kernel used by Aurora
  - Source image: `ghcr.io/ublue-os/aurora:latest`
  - Kernel packages from: `kojipkgs.fedoraproject.org`
  - Example version: `6.17.8-300.fc43.x86_64`

- **bazzite**: Custom Bazzite kernel with gaming optimizations
  - Source image: `ghcr.io/ublue-os/bazzite:latest`
  - Kernel packages from: Bazzite kernel repository
  - Example version: `6.17.7-ba14.fc43.x86_64`

### Manual Trigger Examples

**Build for Both Kernel Types** (default)
```bash
gh workflow run build-rpm.yml
```

**Build for Main Kernel Only**
```bash
gh workflow run build-rpm.yml \
  -f kernel_types=main
```

**Build for Bazzite Kernel Only**
```bash
gh workflow run build-rpm.yml \
  -f kernel_types=bazzite
```

**Build Specific YeetMouse Commit**
```bash
gh workflow run build-rpm.yml \
  -f yeetmouse_commit=99844bbd786d612657d892cac2f663d940fd3d62 \
  -f kernel_types=main,bazzite
```

**Build for Specific Kernel Version**
```bash
gh workflow run build-rpm.yml \
  -f kernel_types=main \
  -f kernel_version=6.11.5-300.fc41.x86_64
```

**Build kmod Only (No CLI)**
```bash
gh workflow run build-rpm.yml \
  -f build_cli=false
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
CONTAINER_IMAGE=ghcr.io/ublue-os/aurora
CONTAINER_VERSION=latest
DEFAULT_KERNEL_TYPE=main
```

**Configuration Options:**
- `CONTAINER_IMAGE`: Default container image for builds
- `CONTAINER_VERSION`: Container image tag/version
- `DEFAULT_KERNEL_TYPE`: Default kernel type when not specified (main or bazzite)

### Container Requirements

The workflow fetches kernel-devel packages dynamically based on kernel type:

- **Main kernel type**: Downloads kernel-devel from Fedora Koji repositories
- **Bazzite kernel type**: Downloads kernel-devel from Bazzite kernel repository

The container image should have basic build tools installed. The workflow installs kernel-devel packages as needed during the build process.

## Build Inputs

The `build-rpm.yml` workflow accepts these inputs:

- `kernel_types` (string, default: "main") - Comma-separated list of kernel types to build (main, bazzite, or main,bazzite)
- `kernel_version` (string, optional) - Specific kernel version to build for. If not provided, auto-detects from distribution images
- `yeetmouse_commit` (string, optional) - YeetMouse commit to build (e.g., 99844bbd786d612657d892cac2f663d940fd3d62). If not provided, uses commit from `.external_versions`
- `build_kmod` (boolean, default: true) - Build kmod package
- `build_cli` (boolean, default: true) - Build CLI package (only built for main kernel type)
- `container_image` (string, optional) - Container image to use (overrides build.conf default)
- `fedora_version` (string, optional) - Container version tag (overrides build.conf default)

### Important Notes

- **Spec files are never modified**: All version and release information is passed via RPM macros
- **Release numbers are automatic**: The workflow queries existing releases and increments appropriately
- **CLI is built once**: Only the main kernel type matrix job builds the CLI package
- **Matrix builds**: Each kernel type builds in parallel for faster execution

### Version and Release Management

- **YeetMouse commit**: Passed to rpmbuild via `--define "commit X...X"`
- **Release number**: Automatically determined by querying GitHub releases
  - Same version + kernel: Increments release number
  - New version or kernel: Resets to release 1
- **Kernel version**: Passed to rpmbuild via `--define "kernel_version X.Y.Z-REL"`

**Example package names:**
- `kmod-yeetmouse-0.9.2-1.6.17.8-300.fc43.x86_64.rpm` (main kernel)
- `kmod-yeetmouse-0.9.2-1.6.17.7-ba14.fc43.x86_64.rpm` (bazzite kernel)
- `yeetmouse-0.9.2-1.fc43.x86_64.rpm` (CLI)

## Matrix Build Strategy

The workflow uses GitHub Actions matrix strategy to build packages for multiple kernel types in parallel.

### How It Works

1. **Matrix Generation**: The `generate-matrix` job creates a build matrix based on the `kernel_types` input
2. **Version Resolution**: Each matrix job resolves its kernel version from the appropriate distribution image
3. **Parallel Builds**: Matrix jobs run in parallel, each building kmod for its kernel type
4. **CLI Handling**: Only the main kernel type matrix job builds the CLI package
5. **Artifact Collection**: The publish job downloads all artifacts and publishes them together

### Matrix Configuration

**Example matrix for `kernel_types=main,bazzite`:**
```json
{
  "include": [
    {
      "kernel_type": "main",
      "build_cli": "true"
    },
    {
      "kernel_type": "bazzite",
      "build_cli": "false"
    }
  ]
}
```

### Benefits

- **Parallel execution**: Faster builds when building for multiple kernel types
- **Isolation**: Each kernel type builds independently
- **Clear logs**: Separate logs for each kernel type
- **Automatic retry**: GitHub Actions handles retries per matrix job
- **No race conditions**: Artifacts are uploaded separately and merged during publish

### Package Naming

Packages are named to include the full kernel version, ensuring uniqueness:

- `kmod-yeetmouse-{version}-{release}.{kernel_version}.rpm`
- Example: `kmod-yeetmouse-0.9.2-1.6.17.8-300.fc43.x86_64.rpm`

This allows multiple kmod packages for different kernels to coexist in the repository.

## Troubleshooting Workflows

### Kernel Version Resolution Failures

**Problem**: Workflow fails to resolve kernel version from image

**Solutions**:
```bash
# Check if the image exists and is accessible
skopeo inspect docker://ghcr.io/ublue-os/aurora:latest

# Verify the ostree.linux label is present
skopeo inspect docker://ghcr.io/ublue-os/aurora:latest | jq '.Labels."ostree.linux"'

# For manual builds, specify kernel version explicitly
gh workflow run build-rpm.yml \
  -f kernel_types=main \
  -f kernel_version=6.17.8-300.fc43.x86_64
```

### Kernel-devel Package Not Found

**Problem**: Workflow fails to download kernel-devel packages

**Solutions**:
```bash
# For main kernel: Check if packages exist in Koji
# Visit: https://kojipkgs.fedoraproject.org/packages/kernel/

# For bazzite kernel: Check Bazzite kernel releases
# Visit: https://github.com/bazzite-org/kernel-bazzite/releases

# If packages are not available, wait for them to be published
# or use a different kernel version that has packages available
```

### Build Failures

**Problem**: RPM build fails during compilation

**Solutions**:
- Check the build logs in the GitHub Actions workflow run
- Look for compilation errors in the "Build kmod-yeetmouse" step
- Verify that kernel-devel was installed correctly
- Check that the YeetMouse source version is compatible with the kernel version

### Release Number Conflicts

**Problem**: Release number determination fails or produces unexpected results

**Solutions**:
```bash
# Manually check existing releases
gh release list

# View packages in a specific release
gh release view build-v0.9.2

# If needed, delete problematic releases and rebuild
gh release delete build-v0.9.2
```

### Matrix Build Failures

**Problem**: One kernel type builds successfully but another fails

**Solutions**:
- Check the logs for the failing matrix job
- Matrix jobs are independent, so one can fail while others succeed
- The publish job will only run if all matrix jobs succeed
- Fix the issue for the failing kernel type and re-run the workflow

### Signing Failures

**Problem**: Package signing fails during publish

**Solutions**:
- Verify GPG secrets are configured correctly in repository settings
- Check that `GPG_PRIVATE_KEY` is base64-encoded
- Verify `GPG_PASSPHRASE` is correct
- Ensure `GPG_KEY_ID` matches the private key

### Version File Issues

**Problem**: `.external_versions` file is out of sync or missing

**Solutions**:
```bash
# Recreate the file manually
cat > .external_versions << EOF
YEETMOUSE_COMMIT=99844bbd786d612657d892cac2f663d940fd3d62
AURORA_KERNEL_VERSION=6.17.8-300.fc43.x86_64
BAZZITE_KERNEL_VERSION=6.17.7-ba14.fc43.x86_64
EOF

# Commit and push
git add .external_versions && \
  git commit -m "chore: recreate external versions file" && \
  git push
```

### Workflow Not Triggering

**Problem**: Changes to `.external_versions` don't trigger builds

**Solutions**:
- The `check-release.yml` workflow runs on a schedule (daily)
- To trigger immediately, manually run the workflow:
  ```bash
  gh workflow run check-release.yml
  ```
- Or manually trigger the build workflow:
  ```bash
  gh workflow run build-rpm.yml -f yeetmouse_commit=99844bbd786d612657d892cac2f663d940fd3d62
  ```
