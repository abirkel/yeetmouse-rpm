#!/usr/bin/env python3
"""COPR APIv3 helper for this repo's workflows.

Builds are only ever started through COPR's API by these workflows. COPR's
webhook rebuild is OFF for every package: with all sources at the repo root it
rebuilt every package on every push, republishing unchanged versions. COPR
serves the newest of two same-NEVRA builds, and deleting that newest one drops
the NEVRA from the repo with no fallback (fedora-copr/copr#3262).

Chroots. The project carries one fedora-NN-x86_64 chroot per Fedora release,
plus fedora-rawhide-x86_64, which is never built in. It exists only so that
COPR's "Follow Fedora branching" copies it, with its additional packages, into
each new fedora-NN chroot when Fedora branches. A chroot is a build target
("ready") only if all of these hold:
  - its name is fedora-<number>-x86_64 (never Rawhide);
  - COPR lists it as an active mock chroot (mock-chroots/list);
  - the project's chroot has both kmodtool and kernel-devel in its
    additional packages;
  - its delete_after_days is null (not on the way out).
This script never edits chroots.

A package's "current version-release" is Version and Release from its spec,
without the dist tag, as printed by `spec_version.py evr`, for example
"0^20260803git78dcd0d-1" (Fedora snapshot form). It is published in a chroot
when a build that succeeded IN THAT CHROOT produced a binary package (not the
src record) with exactly that Version and exactly that Release plus the
chroot's dist tag (fcNN). For kmod-yeetmouse it must be the per-kernel package
kmod-yeetmouse-<pinned kernel for that release>. Every build this script
submits targets exactly one chroot.

Subcommands:
  ready-chroots
      Print the ready chroots, space-separated, oldest release first. A
      fedora chroot that is active but not ready is reported as a warning.

  check-chroots
      Exit 1 if any active fedora chroot of the project is not ready, or if
      none is ready. Workflows run it last, so a problem fails the run (and
      sends the email) without blocking builds in the ready chroots.

  release-published PACKAGE VERSION-RELEASE CHROOT
      Print "true" if PACKAGE has a binary package at VERSION-RELEASE
      published in CHROOT, else "false".

  has-kernel-build KERNEL_NVR VERSION-RELEASE CHROOT
      Print "true" if kmod-yeetmouse-KERNEL_NVR at VERSION-RELEASE is
      published in CHROOT, else "false".

  ensure-built [--grace-hours H] CHROOTS PACKAGE=VERSION-RELEASE ...
      CHROOTS is a space-separated list (the output of ready-chroots). For
      every (package, chroot) pair whose current version-release is not
      published there: wait for every build of it in that chroot already
      queued or running, re-check, then submit one build for that chroot,
      wait, and re-check. A failed build produced no package (the kmod spec
      fails before building when the chroot's kernel differs from the pin),
      so the same version-release is simply submitted again on a later run.
      A pair whose submission outcome was unknown is never submitted twice
      in one run. A succeeded build that published a HIGHER version-release
      also counts (a newer main revision was built).
      A kmod-yeetmouse version-release that is published in a chroot but NOT
      for the pinned kernel is an error and is never resubmitted:
      resubmitting would republish yeetmouse-kmod-common.
      A pair that still fails is an error, unless its first failed build at
      this version-release in that chroot (from COPR's build history) is
      less than H hours old (default 0): then it is a warning, because COPR's
      buildroot may still be catching up with Fedora's mirrors. A conflict,
      a missing kernel pin, or a success that published the wrong thing is
      always an error.
      Exit 0 only if every pair is published or within the grace period.

"true"/"false" answers exit 0. Any API error exits non-zero, so a calling step
fails instead of guessing.

Environment:
  COPR_URL, COPR_OWNER, COPR_PROJECT   required
  COPR_LOGIN, COPR_TOKEN     required to submit; reads work without them
  FINISH_TIMEOUT_SECS        default 3600, per wait
  POLL_SECS                  default 30
  RECONCILE_SECS             default 120 (see build submission below)
"""

import base64
import datetime
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spec_version  # noqa: E402

COPR_URL = os.environ["COPR_URL"].rstrip("/")
OWNER = os.environ["COPR_OWNER"]
PROJECT = os.environ["COPR_PROJECT"]
FINISH_TIMEOUT = int(os.environ.get("FINISH_TIMEOUT_SECS", "3600"))
POLL = int(os.environ.get("POLL_SECS", "30"))
RECONCILE_SECS = int(os.environ.get("RECONCILE_SECS", "120"))

KMOD = "kmod-yeetmouse"
REQUIRED_PACKAGES = {"kmodtool", "kernel-devel"}
TARGET_RE = re.compile(r"fedora-([0-9]+)-x86_64")

FAILED_STATES = {"failed", "canceled"}
# States after which a build never changes again.
TERMINAL_STATES = {"succeeded", "failed", "canceled", "skipped", "forked"}

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


# --- chroots -----------------------------------------------------------------

def release_of(chroot):
    """fedora-NN-x86_64 -> NN. Anything else fails closed."""
    m = TARGET_RE.fullmatch(chroot)
    if not m:
        raise SystemExit(f"unsupported chroot {chroot!r}, expected "
                         f"fedora-NN-x86_64")
    return int(m.group(1))


def _dist(chroot):
    return f"fc{release_of(chroot)}"


def _active_mock_chroots():
    return set(_get("mock-chroots/list"))


def _project_chroots():
    proj = _get("project", {"ownername": OWNER, "projectname": PROJECT})
    return set(proj.get("chroot_repos") or {})


def _project_chroot(chroot):
    return _get("project-chroot", {"ownername": OWNER, "projectname": PROJECT,
                                   "chrootname": chroot})


def survey_chroots():
    """Return (ready chroots sorted by release, problems, notes)."""
    active = _active_mock_chroots()
    ready, problems, notes = [], [], []
    mine = sorted((c for c in _project_chroots() if TARGET_RE.fullmatch(c)),
                  key=release_of)
    for chroot in mine:
        if chroot not in active:
            notes.append(f"{chroot}: not an active COPR chroot (end of "
                         f"life), skipped")
            continue
        cfg = _project_chroot(chroot)
        missing = REQUIRED_PACKAGES - set(cfg.get("additional_packages") or [])
        if missing:
            problems.append(
                f"{chroot}: additional packages lack {' '.join(sorted(missing))}. "
                f"Fix with: copr-cli edit-chroot {OWNER}/{PROJECT}/{chroot} "
                f"--packages 'kmodtool kernel-devel'")
            continue
        if cfg.get("delete_after_days") is not None:
            problems.append(f"{chroot}: scheduled for deletion "
                            f"(delete_after_days={cfg['delete_after_days']})")
            continue
        ready.append(chroot)
    newest_active = max((release_of(c) for c in active
                         if TARGET_RE.fullmatch(c)), default=0)
    newest_mine = max((release_of(c) for c in mine), default=0)
    if newest_active > newest_mine:
        problems.append(
            f"COPR offers fedora-{newest_active}-x86_64 but the project's "
            f"newest chroot is fedora-{newest_mine}-x86_64. Fedora branching "
            f"did not reach this project: check that fedora-rawhide-x86_64 "
            f"exists with 'kmodtool kernel-devel' and that Follow Fedora "
            f"branching is on, then add the chroot by hand.")
    return ready, problems, notes


def ready_chroots():
    ready, problems, notes = survey_chroots()
    for n in notes:
        print(n, file=sys.stderr)
    for p in problems:
        print(f"::warning::{p}", file=sys.stderr)
    print(" ".join(ready))
    return 0


def check_chroots():
    ready, problems, notes = survey_chroots()
    for n in notes:
        print(n)
    print(f"ready chroots: {' '.join(ready) or '(none)'}")
    if not ready:
        problems.append("no ready chroot")
    for p in problems:
        print(f"::error::{p}")
    return 1 if problems else 0


# --- builds ------------------------------------------------------------------

def _list_builds(package, limit, offset=0):
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
    return _get("build/list", params)["items"]


def _iter_builds(package):
    """Every build of PACKAGE, newest first."""
    offset = 0
    while True:
        items = _list_builds(package, limit=PAGE_SIZE, offset=offset)
        yield from items
        if len(items) < PAGE_SIZE:
            return
        offset += PAGE_SIZE


def _builds_in(package, chroot):
    """Every build of PACKAGE that included CHROOT, newest first."""
    return [b for b in _iter_builds(package) if chroot in (b.get("chroots") or [])]


_state_cache = {}


def _chroot_state(build, chroot):
    """State of BUILD in CHROOT. A build covering several chroots (a manual
    one) can succeed in one and fail in another, so it is read per chroot.
    A single-chroot build's own state is that chroot's state."""
    if build.get("chroots") == [chroot]:
        return build.get("state")
    key = (int(build["id"]), chroot)
    if key not in _state_cache:
        _state_cache[key] = _get("build-chroot", {"build_id": build["id"],
                                                  "chrootname": chroot})["state"]
    return _state_cache[key]


EVR_RE = re.compile(r"0\^([0-9]{8})git([0-9a-f]{7,10})-([1-9][0-9]*)")
VERSION_RE = re.compile(r"0\^([0-9]{8})git([0-9a-f]{7,10})")


def _valid_date(s):
    try:
        datetime.datetime.strptime(s, "%Y%m%d")
    except ValueError:
        return False
    return True


def parse_evr(evr):
    """'0^20260803git78dcd0d-1' -> structured fields. Exits on anything else."""
    m = EVR_RE.fullmatch(evr)
    if not m or not _valid_date(m.group(1)):
        raise SystemExit(f"bad VERSION-RELEASE {evr!r}, expected "
                         f"0^<YYYYMMDD>git<shortcommit>-<N>")
    version, release = evr.rsplit("-", 1)
    return {"evr": evr, "version": version, "release": release,
            "snapdate": m.group(1),
            "shortcommit": m.group(2), "rel": int(m.group(3))}


def _is_binary(p):
    return p.get("arch") not in (None, "", "src")


def _pkg_matches(p, want, chroot, name=None):
    """True if built-package record P is a binary package at exactly WANT's
    version and release (plus CHROOT's dist), named NAME when given."""
    return (_is_binary(p)
            and p.get("version") == want["version"]
            and p.get("release") == f"{want['release']}.{_dist(chroot)}"
            and (name is None or p.get("name") == name))


_built_cache = {}


def _built(build_id, chroot):
    # A finished build-chroot's package list never changes, so caching within
    # one invocation is safe. Only asked for build-chroots that succeeded.
    key = (int(build_id), chroot)
    if key not in _built_cache:
        _built_cache[key] = _get(
            "build-chroot/built-packages",
            {"build_id": build_id, "chrootname": chroot})["packages"]
    return _built_cache[key]


def _find_published(package, want, chroot, name=None):
    """Id of a build that succeeded in CHROOT and published WANT there (as
    NAME, when given), else 0. Failed build-chroots never count: the backend
    publishes a chroot's results only when that chroot succeeded."""
    for build in _builds_in(package, chroot):
        if build.get("state") not in TERMINAL_STATES:
            continue
        if _chroot_state(build, chroot) != "succeeded":
            continue
        if any(_pkg_matches(p, want, chroot, name)
               for p in _built(build["id"], chroot)):
            return int(build["id"])
    return 0


def kmod_name(chroot, pins):
    n = release_of(chroot)
    if n not in pins:
        raise SystemExit(f"{chroot}: the kmod spec has no kernel pin for fc{n}; "
                         f"run the kernel poller (it adds one)")
    return f"{KMOD}-{pins[n]}"


def release_published(package, evr, chroot):
    want = parse_evr(evr)
    bid = _find_published(package, want, chroot)
    print(f"{package}: {evr} in {chroot}: "
          + (f"published by build {bid}" if bid else "not published"),
          file=sys.stderr)
    print("true" if bid else "false")
    return 0


def has_kernel_build(nvr, evr, chroot):
    want = parse_evr(evr)
    name = f"{KMOD}-{nvr}"
    bid = _find_published(KMOD, want, chroot, name=name)
    print(f"{name}-{evr}: "
          + (f"built by {bid}" if bid else f"no succeeded build in {chroot}"),
          file=sys.stderr)
    print("true" if bid else "false")
    return 0


def _in_flight(package, chroot):
    """Every not-yet-finished build of PACKAGE that includes CHROOT. Scans the
    full history: a truncated scan could miss an old queued build and lead to
    a duplicate."""
    return [int(b["id"]) for b in _builds_in(package, chroot)
            if b.get("state") not in TERMINAL_STATES]


def _latest_id(package):
    items = _list_builds(package, limit=1)
    return int(items[0]["id"]) if items else 0


def _submit(package, chroot):
    """Submit one build of PACKAGE for CHROOT alone. Return (build ids to wait
    on, ambiguous).

    The chroots field is always sent: COPR builds in EVERY project chroot,
    Rawhide included, when it is omitted.

    Never blindly retried. If the outcome is unknown, every build of PACKAGE
    in CHROOT that appears above the pre-submit baseline within
    RECONCILE_SECS is returned, because any of them may be the one this POST
    created; the caller then waits for all of them and never submits again in
    this run. If none appears, fail so the next run starts from a clean state.
    """
    baseline = _latest_id(package)
    try:
        build = _post("package/build", {
            "ownername": OWNER,
            "projectname": PROJECT,
            "package_name": package,
            "chroots": [chroot],
        })
        return [int(build["id"])], False
    except AmbiguousPost as e:
        print(f"{package} {chroot}: submission outcome unknown ({e}); looking "
              f"for builds above {baseline}", file=sys.stderr)
    deadline = time.time() + RECONCILE_SECS
    while time.time() < deadline:
        time.sleep(15)
        above = []
        for b in _iter_builds(package):
            if int(b["id"]) <= baseline:
                break  # newest first: the rest predate the POST
            if chroot in (b.get("chroots") or []):
                above.append(int(b["id"]))
        if above:
            return above, True
    raise SystemExit(f"{package} {chroot}: no build appeared above {baseline} "
                     f"after an ambiguous submission; not resubmitting")


def _wait(builds):
    """builds: {build_id: (package, chroot)}. Return {build_id: final state
    in that chroot}."""
    deadline = time.time() + FINISH_TIMEOUT
    states = {bid: None for bid in builds}
    while states:
        for bid, state in states.items():
            if state in TERMINAL_STATES:
                continue
            pkg, chroot = builds[bid]
            build = _get(f"build/{bid}")
            states[bid] = (_chroot_state(build, chroot)
                           if build.get("state") in TERMINAL_STATES
                           else build.get("state"))
            print(f"{pkg} {chroot}: build {bid}: {states[bid]}")
        if all(s in TERMINAL_STATES for s in states.values()):
            break
        if time.time() >= deadline:
            break
        time.sleep(POLL)
    return states


def _is_newer(p, want, chroot):
    """True if binary record P is at a version-release rpm sorts above WANT:
    a later snapshot date, or the same Version with a higher Release. Records
    in any other format, or with another dist tag, are ignored."""
    if not _is_binary(p):
        return False
    m = VERSION_RE.fullmatch(p.get("version", ""))
    rel = p.get("release", "")
    suffix = f".{_dist(chroot)}"
    if not m or not rel.endswith(suffix):
        return False
    head = rel[:-len(suffix)]
    if not head.isdigit():
        return False
    if m.group(1) > want["snapdate"]:
        return True
    return p["version"] == want["version"] and int(head) > want["rel"]


def _newer_release_from(build_ids, want, chroot):
    """A version-release HIGHER than WANT published in CHROOT by one of these
    succeeded builds, or None. That happens when a newer main revision was
    built because main changed between our read and COPR's checkout. That
    revision's own run covers it."""
    for bid in build_ids:
        for p in _built(bid, chroot):
            if _is_newer(p, want, chroot):
                return f"{p['version']}-{p['release']}"
    return None


def _published(key, want, pins):
    """(build id or 0, conflict message or None) for KEY=(package, chroot)."""
    pkg, chroot = key
    if pkg != KMOD:
        return _find_published(pkg, want, chroot), None
    bid = _find_published(pkg, want, chroot, name=kmod_name(chroot, pins))
    if bid:
        return bid, None
    other = _find_published(pkg, want, chroot)
    if other:
        return 0, (f"{want['evr']} is published in {chroot} by build {other}, "
                   f"but not as {kmod_name(chroot, pins)}. Rebuilding would "
                   f"republish yeetmouse-kmod-common. Raise the kmod Release "
                   f"(the kernel poller does this when the pin changes).")
    return 0, None


def _label(key):
    return f"{key[0]} {key[1]}"


def _settle(todo, builds, states, errors, pins):
    """After a wait, drop every key in TODO that is now published (by any
    build, ours or not) or superseded by a newer release; return the rest as
    {key: (want, our unsuccessful build ids)}."""
    left = {}
    for key, want in todo.items():
        mine = [b for b, k in builds.items() if k == key]
        stuck = [b for b in mine if states.get(b) not in TERMINAL_STATES]
        if stuck:
            errors[key] = ("; ".join(
                f"build {b} still {states.get(b)} after {FINISH_TIMEOUT}s: "
                f"{COPR_URL}/coprs/build/{b}/" for b in stuck), RETRYABLE)
            continue
        bid, conflict = _published(key, want, pins)
        if conflict:
            errors[key] = (conflict, FATAL)
            continue
        if bid:
            print(f"{_label(key)}: {want['evr']} published by build {bid}")
            continue
        ok = [b for b in mine if states.get(b) == "succeeded"]
        newer = _newer_release_from(ok, want, key[1])
        if newer:
            print(f"{_label(key)}: a newer main revision was built and "
                  f"published {newer} instead of {want['evr']}")
            continue
        left[key] = (want, [b for b in mine if states.get(b) != "succeeded"])
    return left


RETRYABLE, FATAL = True, False


def _evr_cmp(a, b):
    """rpm's order for two version-release strings of this format (-1, 0, 1),
    or None if either is not in it. The whole Version is compared the way
    rpm does, including the git<sha> part, then Release."""
    if not (EVR_RE.fullmatch(a or "") and EVR_RE.fullmatch(b or "")):
        return None
    (va, ra), (vb, rb) = a.rsplit("-", 1), b.rsplit("-", 1)
    return spec_version.rpmvercmp(va, vb) or spec_version.rpmvercmp(ra, rb)


def _failing_for_hours(key, want):
    """Hours since the first failed build of WANT for KEY=(package, chroot),
    read from COPR's own build history (the source package's version is the
    version-release), or 0.0 when none failed yet. This is the durable start
    of the problem across separate workflow runs.

    A build whose SRPM step failed has no source package version. It counts
    when it is newer than every build of a LOWER version-release, since it
    can only have been a build of WANT or of something newer. A version in
    any other format (the pre-snapshot pkgserial scheme) is treated as lower
    too, which is conservative: it can only shorten the grace."""
    pkg, chroot = key
    first = None
    for build in _builds_in(pkg, chroot):  # newest first
        version = (build.get("source_package") or {}).get("version")
        if version and version != want["evr"]:
            order = _evr_cmp(version, want["evr"])
            if order is None or order < 0:
                break  # everything older predates this version-release
            continue  # a newer revision's build
        if build.get("state") not in TERMINAL_STATES:
            continue
        if _chroot_state(build, chroot) not in FAILED_STATES:
            continue
        when = build.get("submitted_on")
        if isinstance(when, (int, float)) and (first is None or when < first):
            first = when
    return 0.0 if first is None else max(0.0, (time.time() - first) / 3600)


def ensure_built(chroots, wanted, grace_hours=0.0, pins=None):
    """chroots: ready chroots. wanted: {package: parsed version-release}.

    1. Skip (package, chroot) pairs already published there.
    2. Wait for every build of the rest already queued or running in that
       chroot (an earlier run's, a manual one), then re-check.
    3. Submit once per pair still missing, wait, re-check. A pair whose
       submission was ambiguous is never submitted twice.
    """
    if not chroots:
        print("::error::no ready chroot to build in")
        return 1
    if pins is None and KMOD in wanted:
        pins = spec_version.kernel_pins(spec_version.read(spec_version.KMOD_SPEC),
                                        spec_version.KMOD_SPEC)
    errors = {}
    todo = {}
    for chroot in chroots:
        for pkg, want in wanted.items():
            key = (pkg, chroot)
            try:
                bid, conflict = _published(key, want, pins)
            except SystemExit as e:
                errors[key] = (str(e), FATAL)  # no kernel pin: a config error
                continue
            if conflict:
                errors[key] = (conflict, FATAL)
            elif bid:
                print(f"{_label(key)}: {want['evr']} already published by "
                      f"build {bid}")
            else:
                todo[key] = want

    builds = {}
    for key in todo:
        for bid in _in_flight(*key):
            print(f"{_label(key)}: waiting for in-flight build {bid}: "
                  f"{COPR_URL}/coprs/build/{bid}/")
            builds[bid] = key
    if builds:
        states = _wait(builds)
        left = _settle(todo, builds, states, errors, pins)
        todo = {key: want for key, (want, _) in left.items()}

    builds = {}
    for key in todo:
        try:
            ids, ambiguous = _submit(*key)
        except SystemExit as e:
            # Keep going so every pair is reported. A rejected or unresolved
            # submission is retried by the next run.
            errors[key] = (str(e), RETRYABLE)
            continue
        for bid in ids:
            print(f"{_label(key)}: {'candidate' if ambiguous else 'submitted'} "
                  f"build {bid}: {COPR_URL}/coprs/build/{bid}/")
            builds[bid] = key
    states = _wait(builds)
    left = _settle({k: todo[k] for k in todo if k not in errors},
                   builds, states, errors, pins)
    for key, (want, bad) in left.items():
        detail = "; ".join(f"build {b} {states.get(b)}: "
                           f"{COPR_URL}/coprs/build/{b}/" for b in bad)
        if detail:
            errors[key] = (f"{want['evr']} not published ({detail})", RETRYABLE)
        else:
            # A success that published something else is not COPR lag.
            errors[key] = (f"{want['evr']} not published although the build "
                           f"succeeded", FATAL)

    failed = 0
    for key, (err, retryable) in errors.items():
        age = (_failing_for_hours(key, todo.get(key) or wanted[key[0]])
               if retryable and grace_hours > 0 else None)
        if age is not None and age < grace_hours:
            print(f"::warning::{_label(key)}: {err}. First failure {age:.1f}h "
                  f"ago (grace {grace_hours:g}h); a later run retries.")
        else:
            print(f"::error::{_label(key)}: {err}")
            failed = 1
    return failed


def _pairs(args):
    out = {}
    for arg in args:
        pkg, sep, evr = arg.partition("=")
        if not sep or not pkg or not evr:
            raise SystemExit(f"bad PACKAGE=VERSION-RELEASE argument: {arg!r}")
        out[pkg] = parse_evr(evr)
    return out


def _chroot_list(arg):
    chroots = arg.split()
    for c in chroots:
        release_of(c)
    if len(set(chroots)) != len(chroots):
        raise SystemExit(f"chroot listed twice: {arg!r}")
    return chroots


def main(argv):
    args = argv[1:]
    if args == ["ready-chroots"]:
        return ready_chroots()
    if args == ["check-chroots"]:
        return check_chroots()
    if len(args) == 4 and args[0] == "release-published":
        release_of(args[3])
        return release_published(args[1], args[2], args[3])
    if len(args) == 4 and args[0] == "has-kernel-build":
        release_of(args[3])
        return has_kernel_build(args[1], args[2], args[3])
    if args and args[0] == "ensure-built":
        rest = args[1:]
        grace = 0.0
        if rest[:1] == ["--grace-hours"] and len(rest) >= 2:
            grace = float(rest[1])
            rest = rest[2:]
        if len(rest) >= 2:
            return ensure_built(_chroot_list(rest[0]), _pairs(rest[1:]), grace)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
