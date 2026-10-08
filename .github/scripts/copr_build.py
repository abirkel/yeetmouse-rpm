#!/usr/bin/env python3
"""Small COPR APIv3 helper for the poller workflows.

Subcommands:
  latest-id PACKAGE
      Print the id of the newest build of PACKAGE in the project, or 0 if the
      package has no builds yet. Run this BEFORE pushing, to get a baseline.

  has-kernel-build KERNEL_NVR CHROOT
      Print "true" or "false": whether a succeeded kmod-yeetmouse build exists
      whose binary subpackage is kmod-yeetmouse-KERNEL_NVR. Non-zero exit only
      on an API error.

  wait COMMIT_SHA PACKAGE=BASELINE_ID [PACKAGE=BASELINE_ID ...]
      For each PACKAGE, collect every build the COPR GitHub webhook queued for
      the push of COMMIT_SHA (duplicates included) until the shared appear
      deadline, and wait for all of them to finish. Exit 0 only if every
      package has at least one such build and all of them succeeded. Exit 1
      if any failed/was canceled, if a package got no webhook build before the
      appear deadline, or if any build did not finish before the shared finish
      deadline. All packages are reported before exiting. Success is therefore
      reported no earlier than the appear deadline.

Build provenance: COPR's GitHub webhook handler submits each rebuild with
committish set to the push payload's "after" SHA, and that value is exposed by
build/source-build-config/<id> as source_dict.committish. A build is only
accepted as ours if its id is above the pre-push baseline AND its committish
equals COMMIT_SHA, so a manual build (committish "main", or a branch name) that
lands in the same window is ignored instead of being mistaken for ours.

Environment:
  COPR_URL, COPR_OWNER, COPR_PROJECT   required
  COPR_LOGIN, COPR_TOKEN               optional (reads on a public project work
                                       without them)
  APPEAR_TIMEOUT_SECS                  default 900, measured from start of wait
  FINISH_TIMEOUT_SECS                  default 3600, measured from start of wait
  POLL_SECS                            default 30
"""

import base64
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

COPR_URL = os.environ["COPR_URL"].rstrip("/")
OWNER = os.environ["COPR_OWNER"]
PROJECT = os.environ["COPR_PROJECT"]
APPEAR_TIMEOUT = int(os.environ.get("APPEAR_TIMEOUT_SECS", "900"))
FINISH_TIMEOUT = int(os.environ.get("FINISH_TIMEOUT_SECS", "3600"))
POLL = int(os.environ.get("POLL_SECS", "30"))

# Terminal states per COPR's build state machine. Anything else (pending,
# importing, starting, running, waiting, forked, skipped...) means keep waiting.
FAILED_STATES = {"failed", "canceled"}

# Transient failures worth retrying: timeouts, connection errors, rate limits
# and server errors. Anything else (401/403 bad token, 404 wrong project) is a
# real misconfiguration and fails immediately.
RETRY_HTTP = {429, 500, 502, 503, 504}
RETRY_ATTEMPTS = 5

# Page size for walking build/list newest-first.
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "50"))


def _get(path, params=None):
    url = f"{COPR_URL}/api_3/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    login, token = os.environ.get("COPR_LOGIN"), os.environ.get("COPR_TOKEN")
    if login and token:
        cred = base64.b64encode(f"{login}:{token}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_HTTP or attempt == RETRY_ATTEMPTS:
                raise
            err = f"HTTP {e.code}"
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            if attempt == RETRY_ATTEMPTS:
                raise
            err = str(e)
        delay = 5 * 2 ** (attempt - 1)
        print(f"  transient COPR API error on {path} ({err}), retry "
              f"{attempt}/{RETRY_ATTEMPTS - 1} in {delay}s", file=sys.stderr)
        time.sleep(delay)


def _list_builds(package, limit, offset=0, status=None):
    # order/order_type are passed explicitly: COPR's Paginator guesses DESC for
    # order=id, but the API's PaginationForm declares order_type default ASC, so
    # relying on the implicit default is ambiguous.
    params = {
        "ownername": OWNER,
        "projectname": PROJECT,
        "packagename": package,
        "limit": limit,
        "offset": offset,
        "order": "id",
        "order_type": "DESC",
    }
    if status:
        params["status"] = status
    return _get("build/list", params)["items"]


def latest_id(package):
    items = _list_builds(package, limit=1)
    return int(items[0]["id"]) if items else 0


_committish_cache = {}


def _committish(build_id):
    # A build's source config never changes, so fetch it once per build.
    if build_id not in _committish_cache:
        cfg = _get(f"build/source-build-config/{build_id}")
        _committish_cache[build_id] = cfg.get("source_dict", {}).get("committish")
    return _committish_cache[build_id]


def _find_webhook_builds(package, baseline, sha):
    """Return (id, submitted_on) for ALL builds of PACKAGE above BASELINE built from SHA.

    Pages through builds newest-first until reaching one at or below the
    baseline, so a burst of unrelated builds above the baseline can never push
    ours off a fixed-size page. All matches are returned, so a duplicate
    webhook delivery for the same SHA is watched too, not silently ignored.
    """
    matches, offset, page_size = [], 0, PAGE_SIZE
    while True:
        items = _list_builds(package, limit=page_size, offset=offset)
        for build in items:
            bid = int(build["id"])
            if bid <= baseline:
                return matches  # DESC order: the rest predate the push
            if _committish(bid) == sha:
                matches.append((bid, build.get("submitted_on") or 0))
        if len(items) < page_size:
            return matches
        offset += page_size


def wait(sha, baselines):
    """Watch every webhook build for SHA, for every package.

    The set of builds judged per package is defined by COPR's own timestamp:
    every matching build SUBMITTED at or before the appear deadline. Discovery
    keeps scanning until it has done at least one scan that started after the
    deadline, so a build submitted just before the deadline is never missed,
    and a build submitted after it is never admitted, however the polling
    passes happen to line up with the deadline.

    A package passes only when that final scan is done, at least one matching
    build exists, and EVERY matching build succeeded. Any failed/canceled match
    fails the package. Every package is reported before exiting.
    """
    start = time.time()
    appear_deadline = start + APPEAR_TIMEOUT
    finish_deadline = start + FINISH_TIMEOUT
    states = {pkg: {} for pkg in baselines}  # pkg -> {build_id: last state}
    frozen = {pkg: False for pkg in baselines}  # final post-deadline scan done
    result = {}  # pkg -> "succeeded" or an error string

    while len(result) < len(baselines):
        for pkg, baseline in baselines.items():
            if pkg in result:
                continue
            if not frozen[pkg]:
                scan_started = time.time()
                for bid, submitted_on in _find_webhook_builds(pkg, baseline, sha):
                    if submitted_on > appear_deadline or bid in states[pkg]:
                        continue
                    states[pkg][bid] = None
                    print(f"{pkg}: webhook build {bid} for {sha[:7]}: "
                          f"{COPR_URL}/coprs/build/{bid}/")
                if scan_started >= appear_deadline:
                    frozen[pkg] = True
            now = time.time()
            collecting = not frozen[pkg]
            if not states[pkg]:
                if collecting:
                    print(f"{pkg}: no build for {sha[:7]} above {baseline} yet")
                else:
                    result[pkg] = (f"no webhook build for {sha} appeared within "
                                   f"{APPEAR_TIMEOUT}s (baseline {baseline}). "
                                   f"Is the webhook wired up?")
                continue
            for bid, state in list(states[pkg].items()):
                if state == "succeeded" or state in FAILED_STATES:
                    continue
                states[pkg][bid] = _get(f"build/{bid}")["state"]
                print(f"{pkg}: build {bid}: {states[pkg][bid]}")
            failed = [b for b, s in states[pkg].items() if s in FAILED_STATES]
            pending = [b for b, s in states[pkg].items()
                       if s != "succeeded" and s not in FAILED_STATES]
            if failed:
                result[pkg] = "; ".join(
                    f"build {b} {states[pkg][b]}: {COPR_URL}/coprs/build/{b}/"
                    for b in failed)
            elif pending and now >= finish_deadline:
                result[pkg] = "; ".join(
                    f"build {b} still {states[pkg][b]} after {FINISH_TIMEOUT}s: "
                    f"{COPR_URL}/coprs/build/{b}/" for b in pending)
            elif not pending and not collecting:
                result[pkg] = "succeeded"
        if len(result) < len(baselines):
            time.sleep(POLL)

    rc = 0
    for pkg in baselines:
        if result[pkg] == "succeeded":
            print(f"{pkg}: all webhook builds for {sha[:7]} succeeded: "
                  f"{sorted(states[pkg])}")
        else:
            rc = 1
            print(f"::error::{pkg}: {result[pkg]}")
    return rc


def has_kernel_build(nvr, chroot):
    """Print "true" if a SUCCEEDED kmod-yeetmouse build exists for kernel NVR,
    else "false". Always exits 0 on a clean answer; any API error raises and
    exits non-zero, so the calling step fails instead of guessing.

    Build-level metadata does not carry the kernel version (source_package is
    only {name, version, url}). The kernel NVR is in the kmodtool-generated
    binary subpackage name, e.g. "kmod-yeetmouse-7.2.9-200.fc44.x86_64",
    returned by build-chroot/built-packages as {"packages": [{name, ...}]}
    (shape confirmed live against build 11093126).
    """
    want = f"kmod-yeetmouse-{nvr}"
    offset, page_size = 0, 100
    while True:
        items = _list_builds("kmod-yeetmouse", limit=page_size, offset=offset,
                             status="succeeded")
        for build in items:
            # Re-check state client-side too, in case the server ignores the
            # status filter.
            if build.get("state") != "succeeded":
                continue
            pkgs = _get("build-chroot/built-packages",
                        {"build_id": build["id"], "chrootname": chroot})["packages"]
            if any(p["name"] == want for p in pkgs):
                print(f"build {build['id']} built {want}", file=sys.stderr)
                print("true")
                return 0
        if len(items) < page_size:
            break
        offset += page_size
    print(f"no succeeded build of {want} in {chroot}", file=sys.stderr)
    print("false")
    return 0


def _parse_baselines(args):
    baselines = {}
    for arg in args:
        pkg, sep, base = arg.partition("=")
        if not sep or not pkg or not base.isdigit():
            raise SystemExit(f"bad PACKAGE=BASELINE_ID argument: {arg!r}")
        baselines[pkg] = int(base)
    return baselines


def main(argv):
    if len(argv) == 3 and argv[1] == "latest-id":
        print(latest_id(argv[2]))
        return 0
    if len(argv) >= 4 and argv[1] == "wait":
        sha = argv[2]
        if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
            raise SystemExit(f"COMMIT_SHA must be a full 40-char hex SHA: {sha!r}")
        return wait(sha, _parse_baselines(argv[3:]))
    if len(argv) == 4 and argv[1] == "has-kernel-build":
        return has_kernel_build(argv[2], argv[3])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
