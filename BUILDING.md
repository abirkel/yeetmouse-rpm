# Building Locally

This guide covers how to build the YeetMouse RPM packages on your own Fedora system. Published packages are built by COPR, see [How COPR builds the packages](#how-copr-builds-the-packages).

## Packages

- `specs/kmod-yeetmouse.spec`: kernel module, built per kernel version with `kmodtool`
- `specs/yeetmouse.spec`: `yeetmouse` CLI tool and service
- `specs/yeetmouse-gui.spec`: GUI

All non-Source0 files the specs use (`config.h`, `yeetmouse.service`, `yeetmouse-preset.conf`, `yeetmouse-sysusers.conf`, `yeetmouse.conf`) live at the repository root, so the repository root is the RPM source directory.

## Prerequisites

```bash
sudo dnf install rpm-build rpmdevtools rpmlint kmodtool kernel-devel \
                 gcc gcc-c++ make git glfw-devel mesa-libGL-devel
```

`kmod-yeetmouse.spec` builds against every `kernel-devel` version installed at the time the spec is parsed. To build for your running kernel, install the matching one:

```bash
sudo dnf install "kernel-devel-$(uname -r)"
```

## Build

```bash
git clone https://github.com/abirkel/yeetmouse-rpm.git
cd yeetmouse-rpm

# Download Source0 (the upstream YeetMouse tarball pinned by %global commit)
spectool -g -C . specs/kmod-yeetmouse.spec
spectool -g -C . specs/yeetmouse.spec
spectool -g -C . specs/yeetmouse-gui.spec

# Build, using the repository root as the source directory
rpmbuild -ba --define "_sourcedir $PWD" specs/kmod-yeetmouse.spec
rpmbuild -ba --define "_sourcedir $PWD" specs/yeetmouse.spec
rpmbuild -ba --define "_sourcedir $PWD" specs/yeetmouse-gui.spec

ls -l ~/rpmbuild/RPMS/x86_64/ ~/rpmbuild/SRPMS/
```

The upstream commit is pinned by `%global commit` in each spec. To build a different upstream commit, pass `--define "commit <full-sha>" --define "shortcommit <short-sha>"` to `spectool` and `rpmbuild`.

### Versioning

The specs follow Fedora's [snapshot versioning](https://docs.fedoraproject.org/en-US/packaging-guidelines/Versioning/#_snapshots). Upstream has no releases, so the base version is 0:

- `Version: 0^%{snapdate}git%{shortcommit}`, where `%global snapdate` is the upstream committer date of the pinned commit, in UTC, as `YYYYMMDD`. For example `0^20260803git78dcd0d`.
- `Release: N%{?dist}`, a packaging counter. It goes back to 1 when the pin changes.

A new upstream commit raises the version, because the date sorts first. A packaging-only change to a spec, or to a file it uses, must raise that spec's `Release`. `check-and-build.yml` fails a pull request or push to `main` that changes a package's build inputs without a higher version-release. `.github/scripts/spec_version.py` reads and changes these fields, and `tests/` covers it (`python3 -m unittest discover -s tests`).

### Same-day upstream commits

The snapshot date must go up from one pin to the next. When upstream's newest commit has the same committer date as the current pin, or an older one (after a force-push), the upstream poller refuses it with "non-monotonic snapshot date" and the run fails. Nothing is committed.

To package such a commit, move every spec to the timestamp form `0^<YYYYMMDD>.<HHMMSS>git<shortcommit>`, using the committer time in UTC. rpm sorts it above the plain date form, so no Epoch is needed. Check the order first, for example `rpmdev-vercmp 0^20260803.180604git1234567-1 0^20260803git78dcd0d-1`. The timestamp form also needs matching changes to the patterns in `spec_version.py` and `copr_build.py`.

The kmod binary package is named after the kernel it was built for, for example `kmod-yeetmouse-7.2.9-200.fc44.x86_64`.

## Install a local build

```bash
sudo dnf install ~/rpmbuild/RPMS/x86_64/kmod-yeetmouse-*.rpm \
                 ~/rpmbuild/RPMS/x86_64/yeetmouse-*.rpm \
                 ~/rpmbuild/RPMS/noarch/yeetmouse-kmod-common-*.rpm
```

## Lint

```bash
rpmlint specs/*.spec
```

Before pushing a spec change, also run `rpmspec --parse <spec>`. It catches macro errors, such as an unescaped `%` in `%changelog` text, without a COPR build.

## How COPR builds the packages

Each package is a COPR SCM package using the `make_srpm` method, with webhook rebuilds turned off. The GitHub Actions workflows start every build through COPR's API (see README.md, "Automated Builds"). COPR runs `make -f .copr/Makefile srpm outdir=<dir> spec=<spec>` as root in a `fedora-44-x86_64` mock chroot. For `kmod-yeetmouse.spec` the Makefile installs `kmodtool` and `kernel-devel` first, because the spec needs both at parse time. That covers only the SRPM step. COPR then builds the binary packages in a separate mock chroot and parses the spec again before any `BuildRequires` are installed, so both packages must also be in that chroot's buildroot. The kmod is built against whatever `kernel-devel` that chroot provides.

Every enabled chroot needs `kmodtool` and `kernel-devel` as additional buildroot packages. Without them the kmod build fails with `kmodtool: command not found`. Set them whenever a chroot is added, for example when Fedora 45 is added, and check the result:

```bash
copr-cli edit-chroot abirkel/yeetmouse/fedora-44-x86_64 --packages "kmodtool kernel-devel"
curl -s "https://copr.fedorainfracloud.org/api_3/project-chroot?ownername=abirkel&projectname=yeetmouse&chrootname=fedora-44-x86_64" | python3 -c 'import sys, json; print(json.load(sys.stdin)["additional_packages"])'
```

A new Fedora release is not added automatically, because the project has no Rawhide chroot for COPR's branching to copy. Adding one also means updating `COPR_CHROOT` in the three workflows.

`kmod-yeetmouse.spec` has no `%files`, `%post` or `%postun` for its main package, because kmodtool generates them for each `kmod-yeetmouse-<kernel>` package. When the Fedora target or the kmodtool version changes, check a real COPR build's package list, file ownership and scriptlets (`rpm -qp --list --scripts`) to confirm that each per-kernel package still owns its module and runs `depmod`, and that no binary package other than `kmod-yeetmouse-<kernel>` and `yeetmouse-kmod-common` is built. The source package is named `yeetmouse-kmod`, so that name is expected only as the `.src.rpm`.

## Troubleshooting

**Missing kernel-devel**

```bash
sudo dnf install "kernel-devel-$(uname -r)"
dnf list --available kernel-devel
```

**Module fails to load after installation**

```bash
ls -la "/lib/modules/$(uname -r)/extra/yeetmouse/"
sudo modprobe -v yeetmouse
sudo dmesg | grep yeetmouse
modinfo yeetmouse | grep signature   # if Secure Boot is enabled
```

**kmod package does not match the running kernel**

Install `kernel-devel` for your running kernel and rebuild `kmod-yeetmouse.spec` as shown above.

## Package signing

COPR signs published packages with its own per-project GPG key, and `dnf` imports the key the first time you install from the COPR repository. No signing key needs to be configured.

The GitHub Actions workflows need two repository secrets to submit builds: `COPR_LOGIN` and `COPR_TOKEN`, from the API token page on COPR (Account, API). COPR tokens expire, so renew them before the expiry date shown there.
