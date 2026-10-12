#!/usr/bin/env bash
# Print "fcNN=<newest kernel-devel NVR>" for each chroot named in $1
# (space-separated fedora-NN-x86_64 names), space-separated. Each release is
# read in its own stock quay.io/fedora/fedora:NN container, from the fedora
# and updates repositories only, so every pin comes from what that release's
# COPR chroot builds from.
#
# This is what the pollers pin. COPR's buildroot can lag the mirror this
# container used; the kmod spec then fails the build before producing any
# package, and the next poll retries the same version-release.
#
# Environment: CONTAINER_RUNTIME (default docker).
set -euo pipefail

runtime=${CONTAINER_RUNTIME:-docker}
out=()
for chroot in $1; do
  if ! [[ "$chroot" =~ ^fedora-([0-9]+)-x86_64$ ]]; then
    echo "::error::unsupported chroot ${chroot}" >&2
    exit 1
  fi
  n=${BASH_REMATCH[1]}
  # Only the fedora and updates repositories: that is what COPR's chroots
  # build from. A branched release's image also enables updates-testing,
  # which carries kernels COPR never sees (probe build 11111425 failed on
  # 7.2.9-301.fc45 from updates-testing while COPR had 7.2.9-300.fc45).
  nvr=$("$runtime" run --rm "quay.io/fedora/fedora:${n}" \
        dnf -q repoquery --repo=fedora --repo=updates --latest-limit=1 \
        --arch=x86_64 --qf '%{version}-%{release}.%{arch}\n' kernel-devel | tail -n1)
  # Same strict format the pins require, for this release only.
  if ! [[ "$nvr" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9a-z.]+\.fc${n}\.x86_64$ ]]; then
    echo "::error::fedora:${n}: unexpected kernel-devel NVR '${nvr}'" >&2
    exit 1
  fi
  echo "fedora:${n}: kernel-devel ${nvr}" >&2
  out+=("fc${n}=${nvr}")
done
echo "${out[*]}"
