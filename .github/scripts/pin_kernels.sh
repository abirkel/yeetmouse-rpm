#!/usr/bin/env bash
# Move the kmod spec's kernel pins to the kernels just sensed, raise the kmod
# Release in the same commit, and push to main. Used by poll-kernel-bump.yml,
# and run by tests/test_pin_kernels.py against a throwaway repository.
#
# Environment: KERNEL_PINS ("fcNN=NVR ...", from sense_kernels.sh). Run from
# the repository root with an "origin" remote.
#
# Pins only move forward (set-kernels --only-newer), and a release with no
# pin yet (a new chroot) gets one. Exit 0 when no pin changed (nothing is
# committed) or the bump was pushed. Exit 1 when the push keeps failing.
set -euo pipefail

: "${KERNEL_PINS:?}"
SPEC=specs/kmod-yeetmouse.spec

# Decide from the live main on every attempt. If a push is rejected, start
# again from the new main and re-apply. Re-applying instead of rebasing
# avoids conflicts on the version lines.
for attempt in 1 2 3; do
  git fetch origin main
  git reset --hard origin/main
  # shellcheck disable=SC2086  # KERNEL_PINS is space-separated on purpose
  python3 .github/scripts/spec_version.py set-kernels --only-newer $KERNEL_PINS
  if git diff --quiet -- "$SPEC"; then
    echo "kernel pins are current"
    exit 0
  fi
  # A pin change is a spec change: it always gets a new Release, so no
  # version-release is ever published for two different kernels.
  python3 .github/scripts/spec_version.py bump-release kmod-yeetmouse
  pins=$(python3 .github/scripts/spec_version.py kernel-pins)
  git add "$SPEC"
  git commit -m "chore: pin kmod-yeetmouse kernels ${pins}"
  if git push origin HEAD:refs/heads/main; then
    exit 0
  fi
  echo "push rejected (attempt ${attempt}), retrying from the new main"
  sleep $((attempt * ${PUSH_RETRY_SLEEP:-10}))
done
echo "::error::Could not push the kernel pin bump after 3 attempts"
exit 1
