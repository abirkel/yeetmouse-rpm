#!/usr/bin/env python3
"""COPR APIv3 helper for this repo's workflows.

Builds are only ever started through COPR's API by these workflows. COPR's
webhook rebuild is OFF for every package: with all sources at the repo root it
rebuilt every package on every push, republishing unchanged versions. COPR
serves the newest of two same-NEVRA builds, and deleting that newest one drops
the NEVRA from the repo with no fallback (fedora-copr/copr#3262).

A package's "current release" is the Release in its spec without the dist tag,
as printed by `spec_version.py release-prefix`, e.g. "3.20260803git78dcd0d".
Every package is Version 0.

Subcommands:
  release-published PACKAGE RELEASE_PREFIX
      Print "true" if a succeeded build of PACKAGE produced any binary package
      at version 0 and RELEASE_PREFIX, else "false".

  has-kernel-build KERNEL_NVR RELEASE_PREFIX
      Print "true" if a succeeded kmod-yeetmouse build produced
      kmod-yeetmouse-KERNEL_NVR at version 0 and RELEASE_PREFIX, else "false".

  ensure-built PACKAGE=RELEASE_PREFIX [PACKAGE=RELEASE_PREFIX ...]
      For every PACKAGE whose current release is not yet published: wait for
      every build of it already queued or running, re-check, then submit one
      build for what is still missing, wait, and re-check. Publication by ANY
      build counts, so a concurrent build is never duplicated. A package whose
      submission outcome was unknown is never submitted twice in one run.
      A succeeded build that published a HIGHER serial (main moved on before
      COPR checked it out) also counts; the newer main's run covers it.
      Exit 0 only if every package ends up published.
      Packages already published are skipped, so this is safe to run on every
      push and every poll.

"true"/"false" answers exit 0. Any API error exits non-zero, so a calling step
fails instead of guessing.

Environment:
  COPR_URL, COPR_OWNER, COPR_PROJECT, COPR_CHROOT   required
  COPR_LOGIN, COPR_TOKEN     required to submit; reads work without them
  FINISH_TIMEOUT_SECS        default 3600, per wait
  POLL_SECS                  default 30
  RECONCILE_SECS             default 120 (see build submission below)
"""

import base64
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

COPR_URL = os.environ["COPR_URL"].rstrip("/")
OWNER = os.environ["COPR_OWNER"]
PROJECT = os.environ["COPR_PROJECT"]
CHROOT = os.environ["COPR_CHROOT"]
FINISH_TIMEOUT = int(os.environ.get("FINISH_TIMEOUT_SECS", "3600"))
POLL = int(os.environ.get("POLL_SECS", "30"))
RECONCILE_SECS = int(os.environ.get("RECONCILE_SECS", "120"))

FAILED_STATES = {"failed", "canceled"}
# States after which a build never changes again.
TERMINAL_STATES = {"succeeded", "failed", "canceled", "skipped"}

# Transient read failures worth retrying. Anything else (401/403 bad token,
# 404 wrong project) is a real misconfiguration and fails immediately.
RETRY_HTTP = {429, 500, 502, 503, 504}
RETRY_ATTEMPTS = 5

PAGE_SIZE = int(os.environ.get("PAGE_SIZE", "50"))


def _auth_header():
    login, token = os.environ.get("COPR_LOGIN"), os.environ.get("COPR_TOKEN")
    if login and token:
        cred = base64.b64encode(f"{login}:{token}".encode()).decode()
        return f"Basic {cred}"
    return None


def _get(path, params=None):
    url = f"{COPR_URL}/api_3/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    auth = _auth_header()
    if auth:
        req.add_header("Authorization", auth)
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


class AmbiguousPost(Exception):
    """The request may or may not have reached COPR."""


def _post(path, body):
    """POST a JSON body. Never retried: a definite rejection (4xx) exits, and
    a transport failure or 5xx raises AmbiguousPost, because COPR may have
    created the build anyway."""
    auth = _auth_header()
    if not auth:
        raise SystemExit("COPR_LOGIN and COPR_TOKEN are required to submit a build")
    req = urllib.request.Request(
        f"{COPR_URL}/api_3/{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Accept": "application/json",
                 "Content-Type": "application/json",
                 "Authorization": auth})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:2000]
        if e.code >= 500:
            raise AmbiguousPost(f"HTTP {e.code}: {detail}") from e
        raise SystemExit(f"COPR POST {path} failed: HTTP {e.code}: {detail}")
    except (urllib.error.URLError, socket.timeout, TimeoutError,
            ConnectionError, json.JSONDecodeError) as e:
        raise AmbiguousPost(str(e)) from e


def _list_builds(package, limit, offset=0, status=None):
    # order/order_type are explicit: COPR's Paginator guesses DESC for
    # order=id, but the API form declares order_type default ASC.
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


def _iter_builds(package, status=None):
    """Every build of PACKAGE, newest first."""
    offset = 0
    while True:
        items = _list_builds(package, limit=PAGE_SIZE, offset=offset,
                             status=status)
        yield from items
        if len(items) < PAGE_SIZE:
            return
        offset += PAGE_SIZE


def _release_matches(release, prefix):
    # release is "<prefix>.<dist>", e.g. "3.20260803git78dcd0d.fc44". This
    # project only targets fedora-*-x86_64 chroots, whose dist is "fcNN".
    # A new chroot family with another dist format must update this check.
    if not release.startswith(prefix + "."):
        return False
    return re.fullmatch(r"fc[0-9]+", release[len(prefix) + 1:]) is not None


_built_cache = {}


def _built(build_id):
    # A finished build's package list never changes; callers only ask about
    # succeeded builds, so caching within one invocation is safe. Cost is one
    # request per succeeded build of the package per invocation, which stays
    # in the low hundreds for this project's build rate.
    if build_id not in _built_cache:
        _built_cache[build_id] = _get(
            "build-chroot/built-packages",
            {"build_id": build_id, "chrootname": CHROOT})["packages"]
    return _built_cache[build_id]


def _build_has(build_id, prefix, name=None):
    """True if build BUILD_ID produced a package at version 0 and PREFIX
    (named NAME, when given)."""
    return any(p.get("version") == "0"
               and _release_matches(p.get("release", ""), prefix)
               and (name is None or p.get("name") == name)
               for p in _built(build_id))


def _find_published(package, prefix, name=None):
    for build in _iter_builds(package, status="succeeded"):
        # Re-check state client-side in case the server ignores the filter.
        if build.get("state") != "succeeded":
            continue
        if _build_has(build["id"], prefix, name):
            return int(build["id"])
    return 0


def release_published(package, prefix):
    bid = _find_published(package, prefix)
    print(f"{package}: release {prefix} "
          + (f"published by build {bid}" if bid else "not published"),
          file=sys.stderr)
    print("true" if bid else "false")
    return 0


def has_kernel_build(nvr, prefix):
    want = f"kmod-yeetmouse-{nvr}"
    bid = _find_published("kmod-yeetmouse", prefix, name=want)
    print(f"{want}-0-{prefix}: "
          + (f"built by {bid}" if bid else f"no succeeded build in {CHROOT}"),
          file=sys.stderr)
    print("true" if bid else "false")
    return 0


def _in_flight(package):
    """Every not-yet-finished build of PACKAGE. Scans the full history: a
    truncated scan could miss an old queued build and lead to a duplicate."""
    return [int(b["id"]) for b in _iter_builds(package)
            if b.get("state") not in TERMINAL_STATES]


def _latest_id(package):
    items = _list_builds(package, limit=1)
    return int(items[0]["id"]) if items else 0


def _submit(package):
    """Submit one build of PACKAGE. Return (build ids to wait on, ambiguous).

    Never blindly retried. If the outcome is unknown, every build that appears
    above the pre-submit baseline within RECONCILE_SECS is returned, because
    any of them may be the one this POST created; the caller then waits for
    all of them and never submits again in this run. If none appears, fail so
    the next run starts from a clean state.
    """
    baseline = _latest_id(package)
    try:
        build = _post("package/build", {
            "ownername": OWNER,
            "projectname": PROJECT,
            "package_name": package,
        })
        return [int(build["id"])], False
    except AmbiguousPost as e:
        print(f"{package}: submission outcome unknown ({e}); looking for "
              f"builds above {baseline}", file=sys.stderr)
    deadline = time.time() + RECONCILE_SECS
    while time.time() < deadline:
        time.sleep(15)
        above = []
        for b in _iter_builds(package):
            if int(b["id"]) <= baseline:
                break  # newest first: the rest predate the POST
            above.append(int(b["id"]))
        if above:
            return above, True
    raise SystemExit(f"{package}: no build appeared above {baseline} after "
                     f"an ambiguous submission; not resubmitting")


def _wait(builds):
    """builds: {build_id: package}. Return {build_id: final state}."""
    deadline = time.time() + FINISH_TIMEOUT
    states = {bid: None for bid in builds}
    while states:
        for bid, state in states.items():
            if state in TERMINAL_STATES:
                continue
            states[bid] = _get(f"build/{bid}")["state"]
            print(f"{builds[bid]}: build {bid}: {states[bid]}")
        if all(s in TERMINAL_STATES for s in states.values()):
            break
        if time.time() >= deadline:
            break
        time.sleep(POLL)
    return states


def _serial(release):
    head = release.split(".", 1)[0]
    return int(head) if head.isdigit() else -1


def _newer_release_from(build_ids, prefix):
    """A release with a HIGHER serial than PREFIX published by one of these
    succeeded builds, or None. That happens when main moved on between our
    read and COPR's checkout; the newer main's own run covers its release."""
    want = _serial(prefix)
    for bid in build_ids:
        for p in _built(bid):
            rel = p.get("release", "")
            if p.get("version") == "0" and _serial(rel) > want:
                return rel
    return None


def _settle(wanted, todo, builds, states, errors):
    """After a wait, drop every package in TODO that is now published (by any
    build, ours or not) or superseded by a newer release; return the rest."""
    left = {}
    for pkg, prefix in todo.items():
        mine = [b for b, p in builds.items() if p == pkg]
        stuck = [b for b in mine if states.get(b) not in TERMINAL_STATES]
        if stuck:
            errors[pkg] = "; ".join(
                f"build {b} still {states.get(b)} after {FINISH_TIMEOUT}s: "
                f"{COPR_URL}/coprs/build/{b}/" for b in stuck)
            continue
        bid = _find_published(pkg, prefix)
        if bid:
            print(f"{pkg}: 0-{prefix} published by build {bid}")
            continue
        ok = [b for b in mine if states.get(b) == "succeeded"]
        newer = _newer_release_from(ok, prefix)
        if newer:
            print(f"{pkg}: main moved on; build published newer 0-{newer} "
                  f"instead of 0-{prefix}")
            continue
        left[pkg] = (prefix, [b for b in mine if states.get(b) != "succeeded"])
    return left


def ensure_built(wanted):
    """wanted: {package: release_prefix}.

    1. Skip packages already published at their release.
    2. Wait for every build of the rest that is already queued or running
       (an earlier run's, a manual one), then re-check publication.
    3. Submit once for what is still missing, wait, re-check publication.
       A package whose submission was ambiguous is never submitted twice.
    """
    errors = {}
    todo = {}
    for pkg, prefix in wanted.items():
        bid = _find_published(pkg, prefix)
        if bid:
            print(f"{pkg}: 0-{prefix} already published by build {bid}")
        else:
            todo[pkg] = prefix

    builds = {}
    for pkg in todo:
        for bid in _in_flight(pkg):
            print(f"{pkg}: waiting for in-flight build {bid}: "
                  f"{COPR_URL}/coprs/build/{bid}/")
            builds[bid] = pkg
    if builds:
        states = _wait(builds)
        left = _settle(wanted, todo, builds, states, errors)
        todo = {pkg: prefix for pkg, (prefix, _) in left.items()}

    builds = {}
    for pkg in todo:
        try:
            ids, ambiguous = _submit(pkg)
        except SystemExit as e:
            errors[pkg] = str(e)  # keep going so every package is reported
            continue
        for bid in ids:
            print(f"{pkg}: {'candidate' if ambiguous else 'submitted'} build "
                  f"{bid}: {COPR_URL}/coprs/build/{bid}/")
            builds[bid] = pkg
    states = _wait(builds)
    left = _settle(wanted, {p: todo[p] for p in todo if p not in errors},
                   builds, states, errors)
    for pkg, (prefix, bad) in left.items():
        detail = "; ".join(f"build {b} {states.get(b)}: "
                           f"{COPR_URL}/coprs/build/{b}/" for b in bad)
        errors[pkg] = (f"0-{prefix} not published"
                       + (f" ({detail})" if detail else
                          " although the build succeeded"))

    for pkg, err in errors.items():
        print(f"::error::{pkg}: {err}")
    return 1 if errors else 0


def _pairs(args):
    out = {}
    for arg in args:
        pkg, sep, prefix = arg.partition("=")
        if not sep or not pkg or not prefix:
            raise SystemExit(f"bad PACKAGE=RELEASE_PREFIX argument: {arg!r}")
        out[pkg] = prefix
    return out


def main(argv):
    if len(argv) == 4 and argv[1] == "release-published":
        return release_published(argv[2], argv[3])
    if len(argv) == 4 and argv[1] == "has-kernel-build":
        return has_kernel_build(argv[2], argv[3])
    if len(argv) >= 3 and argv[1] == "ensure-built":
        return ensure_built(_pairs(argv[2:]))
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
