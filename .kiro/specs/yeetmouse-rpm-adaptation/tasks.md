# Implementation Plan

- [x] 1. Create configuration and tracking files





  - Create build.conf with container image settings and ENABLE_KMOD flag
  - Create yeetmouse.repo file for user installation
  - Prompt user to configure GPG keys and set up GH secrets. Tell them the directions in the maccel-rpm/ docs on this subject so they can follow the necessary stepz.
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 2. Update spec files for commit-based versioning





  - [x] 2.1 Verify %global commit and %global shortcommit variables exist in all spec files


    - Ensure akmod-yeetmouse.spec has commit variables
    - Ensure kmod-yeetmouse.spec has commit variables
    - Ensure yeetmouse-gui.spec has commit variables
    - _Requirements: 2.1, 2.2_
  

  - [x] 2.2 Verify Source0 URLs use commit-based GitHub archive format

    - Check Source0 format: https://github.com/AndyFilter/YeetMouse/archive/%{commit}/YeetMouse-%{commit}.tar.gz
    - Verify all three spec files use consistent Source0 format
    - _Requirements: 2.1, 2.5_
  
  - [x] 2.3 Verify %setup directive matches tarball extraction directory


    - Ensure %setup -q -n YeetMouse-%{commit} is used in all specs
    - Test that spectool can download and extract sources correctly
    - _Requirements: 2.5, 9.5_

- [ ] 3. Copy and adapt check-release.yml workflow
  - [ ] 3.1 Copy workflow file from maccel-rpm
    - Create .github/workflows/ directory
    - Copy maccel-rpm/.github/workflows/check-release.yml to .github/workflows/check-release.yml
    - _Requirements: All workflow-related requirements_
  
  - [ ] 3.2 Update repository references
    - Change "Gnarus-G/maccel" to "AndyFilter/YeetMouse" in all API calls
    - Change "maccel" to "yeetmouse" in variable names and messages
    - Update workflow name to "Check Upstream Versions" (already correct)
    - _Requirements: 1.1_
  
  - [ ] 3.3 Modify release detection to use commits instead of tags
    - Replace "Get latest maccel release" step with commit detection
    - Change from `repos/Gnarus-G/maccel/releases/latest` to `repos/AndyFilter/YeetMouse/commits/main`
    - Extract `.sha` instead of `.tag_name`
    - Calculate short commit (first 7 chars)
    - _Requirements: 1.1, 1.3, 6.2_
  
  - [ ] 3.4 Update .external_versions when commit changes
    - In "Check if release is new" step, when commit differs, update YEETMOUSE_COMMIT
    - Commit and push .external_versions changes
    - Note: DKMS_VER is NOT stored in .external_versions - it's extracted during build from the commit's Makefile
    - _Requirements: 1.2, 5.2, 5.6_
  
  - [ ] 3.5 Update .external_versions variable names
    - Change MACCEL_VERSION to YEETMOUSE_COMMIT
    - Keep KERNEL_VERSION as-is
    - Update all references in load/update/commit steps
    - _Requirements: 5.1, 5.2, 5.3, 5.4_
  
  - [ ] 3.6 Update build trigger parameters
    - Change maccel_version parameter to yeetmouse_commit
    - Pass full commit hash (40 characters) to build trigger
    - Do NOT pass DKMS_VER - it will be extracted during the build from the commit's Makefile
    - Keep build_akmod, build_cli, build_kmod logic as-is
    - _Requirements: 1.5, 6.5, 14.3_

- [ ] 4. Copy and adapt build-rpm.yml workflow
  - [ ] 4.1 Copy workflow file from maccel-rpm
    - Copy maccel-rpm/.github/workflows/build-rpm.yml to .github/workflows/build-rpm.yml
    - _Requirements: All build workflow requirements_
  
  - [ ] 4.2 Update workflow input names
    - Rename maccel_version input to yeetmouse_commit
    - Update description to reference commit hash instead of version tag
    - Keep all other inputs as-is (update_specs, build_akmod, build_cli, build_kmod, container_image, fedora_version)
    - _Requirements: 3.2_
  
  - [ ] 4.3 Update load-config job (keep as-is)
    - No changes needed - already reads build.conf correctly
    - _Requirements: 4.3, 4.4, 4.5_
  
  - [ ] 4.4 Modify update-specs job for commit-based versioning
    - [ ] 4.4.1 Update "Determine maccel version" step
      - Rename to "Determine yeetmouse commit"
      - Change INPUT_VERSION to INPUT_COMMIT
      - Read from yeetmouse_commit input instead of maccel_version
      - Read YEETMOUSE_COMMIT from .external_versions instead of MACCEL_VERSION
      - _Requirements: 5.5_
    
    - [ ] 4.4.2 Add DKMS_VER extraction step
      - After determining commit, download Makefile from that commit
      - Parse DKMS_VER variable with grep/cut
      - Store as VERSION_NUM for spec updates
      - _Requirements: 7.1, 7.3_
    
    - [ ] 4.4.3 Update spec file update logic
      - Add sed commands to update %global commit and %global shortcommit
      - Keep existing Version field update (now uses DKMS_VER)
      - Modify Release field format to include .git{shortcommit}
      - Update changelog message to reference commit hash
      - _Requirements: 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
    
    - [ ] 4.4.4 Update commit message
      - Change from "update spec files to version X" to "update spec files to version X (commit Y)"
      - _Requirements: 7.7_
  
  - [ ] 4.5 Update build-rpm job package names
    - [ ] 4.5.1 Update "Get version from spec" step
      - Change from specs/maccel.spec to specs/akmod-yeetmouse.spec (or any spec)
      - Add step to extract short_commit from spec file
      - Output both version and short_commit
      - _Requirements: 15.1_
    
    - [ ] 4.5.2 Update "Download maccel source" step name
      - Rename to "Download YeetMouse source"
      - Keep spectool logic as-is (reads from spec files)
      - _Requirements: 9.1, 9.3_
    
    - [ ] 4.5.3 Update package build step names
      - Rename "Build akmod-maccel" to "Build akmod-yeetmouse"
      - Change spec file from akmod-maccel.spec to akmod-yeetmouse.spec
      - Rename "Build maccel CLI" to "Build yeetmouse-gui"
      - Change spec file from maccel.spec to yeetmouse-gui.spec
      - Rename "Build kmod-maccel" to "Build kmod-yeetmouse"
      - Change spec file from kmod-maccel.spec to kmod-yeetmouse.spec
      - _Requirements: 3.1, 3.3_
    
    - [ ] 4.5.4 Update package exclusion patterns
      - Change akmod-akmod-maccel to akmod-akmod-yeetmouse
      - Change kmod-akmod-maccel to kmod-akmod-yeetmouse
      - Change kmod-maccel pattern to kmod-yeetmouse in rename logic
      - _Requirements: 3.5, 14.4_
    
    - [ ] 4.5.5 Update package copy patterns
      - Change akmod-maccel-*.rpm to akmod-yeetmouse-*.rpm
      - Change maccel-*.rpm to yeetmouse-gui-*.rpm
      - Change kmod-maccel-*.rpm to kmod-yeetmouse-*.rpm
      - _Requirements: 3.5_
  
  - [ ] 4.6 Update publish job for YeetMouse
    - [ ] 4.6.1 Update release notes template
      - Change "RPM packages for maccel" to "RPM packages for YeetMouse"
      - Add commit hash to release notes
      - Change maccel.repo to yeetmouse.repo in installation instructions
      - Change "dnf install maccel" to "dnf install akmod-yeetmouse yeetmouse-gui"
      - Update post-install message for GUI usage with sudo
      - _Requirements: 10.2, 15.5_
    
    - [ ] 4.6.2 Update release tag format
      - Change from build-${{version}} to build-v${{version}}-${{short_commit}}
      - _Requirements: 10.2_
    
    - [ ] 4.6.3 Keep GitHub Pages deployment as-is
      - No changes needed - already handles merged repository correctly
      - _Requirements: 10.4, 10.5_
  
  - [ ] 4.7 Keep cleanup-on-failure job as-is
    - No changes needed - already works with any spec files
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [ ] 5. Create documentation files
  - [ ] 5.1 Create README.md
    - Add overview of YeetMouse RPM packaging
    - Document three packages: akmod-yeetmouse, kmod-yeetmouse, yeetmouse-gui
    - Explain difference between akmod and kmod
    - Provide repository setup instructions
    - Provide installation instructions
    - Add post-installation steps for GUI usage with sudo
    - Include troubleshooting link
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_
  
  - [ ] 5.2 Create BUILDING.md
    - Document container requirements for kmod builds
    - Explain why full OS images are needed
    - Document build.conf configuration
    - Provide local build instructions
    - Document spec file modification process
    - Include linting instructions
    - Document GitHub Actions secrets setup
    - _Requirements: Documentation for local development_
  
  - [ ] 5.3 Create WORKFLOWS.md
    - Document workflow architecture (five-job structure)
    - Explain automatic build triggers
    - Document manual build options with examples
    - Explain build configuration via build.conf
    - Document workflow inputs and their effects
    - Explain version update behavior
    - _Requirements: Documentation for workflow usage_
  
  - [ ] 5.4 Create TROUBLESHOOTING.md
    - Document common issues and solutions
    - Include kernel module loading problems
    - Include GUI permission issues
    - Include package installation failures
    - Include build failure debugging
    - _Requirements: 12.5_

- [ ] 6. Configure GitHub repository settings
  - [ ] 6.1 Generate and configure GPG secrets
    - Generate GPG key pair for package signing
    - Export private key and encode as base64
    - Add GPG_PRIVATE_KEY secret to repository
    - Add GPG_PASSPHRASE secret to repository
    - Add GPG_KEY_ID secret to repository
    - _Requirements: 10.1_
  
  - [ ] 6.2 Enable GitHub Pages
    - Configure repository to deploy from gh-pages branch
    - Verify Pages URL is accessible
    - _Requirements: 10.4_
  
  - [ ] 6.3 Configure workflow permissions
    - Ensure workflows have write access to contents
    - Ensure workflows have write access to packages
    - _Requirements: Workflow execution_

- [ ]* 7. Test and validate workflows
  - [ ]* 7.1 Test check-release workflow manually
    - Run workflow via workflow_dispatch
    - Verify commit detection works
    - Verify DKMS_VER extraction works
    - Verify .external_versions updates correctly
    - Verify build-rpm workflow triggers
    - _Requirements: All check-release requirements_
  
  - [ ]* 7.2 Test manual build workflow
    - Test building current version (no update_specs)
    - Test building with update_specs=true
    - Test building specific commit
    - Test akmod-only build
    - Test kmod-only build
    - Test GUI-only build
    - _Requirements: All build-rpm requirements_
  
  - [ ]* 7.3 Test failure rollback
    - Introduce intentional build failure
    - Verify cleanup-on-failure triggers
    - Verify spec update commit is reverted
    - Verify repository returns to clean state
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_
  
  - [ ]* 7.4 Test end-to-end user installation
    - Install yeetmouse.repo on test system
    - Install akmod-yeetmouse and yeetmouse-gui packages
    - Verify kernel module loads
    - Verify GUI runs with sudo
    - Verify package signatures
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 12.4_

- [ ] 8. Clean up proof-of-concept files
  - Remove or archive build.sh script
  - Remove or archive container/ directory with Dockerfile and build-inside.sh
  - Remove or archive build-output/ directory
  - Update .gitignore if needed
  - _Requirements: Project cleanup_
