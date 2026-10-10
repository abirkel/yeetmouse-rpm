#!/usr/bin/env bash
# Pin a new upstream YeetMouse commit on main: set the snapshot in all three
# specs (spec_version.py bump-pin), update .external_versions, commit and push.
# Used by poll-upstream-commit.yml, and run by tests/test_pin_upstream.sh
# against a throwaway repository.
#
# Environment: NEW_SHA (40 hex), SNAPDATE (YYYYMMDD, upstream committer date
# in UTC). Run from the repository root with an "origin" remote.
#
# Exit 0 when main already pins NEW_SHA (nothing is committed) or the bump was
# pushed. Exit 1 when bump-pin refuses the date or the push keeps failing.
set -euo pipefail

: "${NEW_SHA:?}" "${SNAPDATE:?}"
SPECS=(specs/kmod-yeetmouse.spec specs/yeetmouse.spec specs/yeetmouse-gui.spec)

# Decide from the live main on every attempt. If a push is rejected, start
# again from the new main and re-apply the bump. Re-applying instead of
# rebasing avoids conflicts on the version lines.
for attempt in 1 2 3; do
  git fetch origin main
  git reset --hard origin/main
  current=$(grep -oP '^YEETMOUSE_COMMIT=\K[0-9a-f]{40}$' .external_versions)
  if [ "$current" = "$NEW_SHA" ]; then
    echo "main already pins ${NEW_SHA}"
    exit 0
  fi
  python3 .github/scripts/spec_version.py bump-pin "$NEW_SHA" "$SNAPDATE"
  # Second line of defense: bump-pin is a no-op when the specs already pin
  # NEW_SHA even if .external_versions disagreed. Never commit nothing.
  if git diff --quiet -- "${SPECS[@]}"; then
    echo "specs already pin ${NEW_SHA}, nothing to commit"
    exit 0
  fi
  sed -i -E "s/^YEETMOUSE_COMMIT=.*/YEETMOUSE_COMMIT=${NEW_SHA}/" .external_versions
  grep -qx "YEETMOUSE_COMMIT=${NEW_SHA}" .external_versions
  git add "${SPECS[@]}" .external_versions
  git commit -m "chore: update yeetmouse commit pin to ${NEW_SHA}"
  if git push origin HEAD:refs/heads/main; then
    exit 0
  fi
  echo "push rejected (attempt ${attempt}), retrying from the new main"
  sleep $((attempt * ${PUSH_RETRY_SLEEP:-10}))
done
echo "::error::Could not push the pin bump after 3 attempts"
exit 1
