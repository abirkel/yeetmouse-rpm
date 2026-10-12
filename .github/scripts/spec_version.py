#!/usr/bin/env python3
"""Read, bump and check the version fields of this repo's three specs.

Every spec carries exactly one of each of these lines (Fedora Versioning
guidelines, Snapshots, form <date><scm><revision>. Upstream has no
releases, so the base version is 0):

  %global commit %{?commit}%{!?commit:<40-hex upstream sha>}
  %global shortcommit %{?shortcommit}%{!?shortcommit:<7-10 hex>}
  %global snapdate <YYYYMMDD, upstream committer date in UTC>
  Version:        0^%{snapdate}git%{shortcommit}
  Release:        <positive integer>%{?dist}

A new upstream commit raises Version (the date sorts first) and resets
Release to 1. A packaging-only change raises Release.

The snapshot date must strictly increase from pin to pin. Two upstream
commits on the same day, or an older date (an upstream force-push), cannot be
ordered by this form, so bump-pin refuses them and a human decides. The
documented fallback is to move every spec to
0^<YYYYMMDD>.<HHMMSS>git<shortcommit>, which rpm sorts above the plain form
(see BUILDING.md).

Subcommands:
  evr SPEC
      Print "<version>-<release>" (no dist), e.g. 0^20260803git78dcd0d-1.

  evrs
      Print "PACKAGE=<version>-<release>" for all three packages,
      space-separated, for copr_build.py.

  bump-pin SHA SNAPDATE
      In all three specs set commit, shortcommit and snapdate, and reset
      Release to 1. The three specs must agree on the pin first. If SHA is
      already pinned, print "already pinned" and change nothing. A SNAPDATE
      that is not strictly later than the current one is refused.

  bump-release PACKAGE
      Add 1 to PACKAGE's Release only. Used by the kernel poller, so a
      kernel-only rebuild never republishes yeetmouse-kmod-common (noarch,
      same NEVR for every kernel) at an already-published version.

  check-bump BASE_REF
      For every package whose build inputs changed between BASE_REF and the
      working tree, require its version-release to be higher than at
      BASE_REF. Exit 1 listing every violation. A spec that does not exist at
      BASE_REF is exempt (a new package). A BASE_REF spec in the one previous
      format (Version 0, pkgserial Release) counts as lower than any snapshot
      version, which is what rpm does too.

  kernel-pins
      Print the kmod spec's kernel pins as "fcNN=<kernel NVR>",
      space-separated, sorted by release.

  set-kernels [--only-newer] fcNN=NVR [fcNN=NVR ...]
      Set (or add) those kernel pins in the kmod spec, leaving other pins
      alone. With --only-newer, a pin only ever moves to a kernel rpm sorts
      higher (a lagging mirror must not move it back). Release is NOT
      changed: the caller raises it in the same commit (bump-release
      kmod-yeetmouse), because a pin change is a spec change.
      Prints "unchanged" when no pin changed.

Kernel pins look like this, one line per Fedora release, in the kmod spec:

  %global target_kernel_fc44 7.2.9-201.fc44.x86_64

The spec fails a binary build when the chroot's kernel-devel is not exactly
the pin for its release, so a lagging COPR buildroot produces no package and
the same version-release can be retried.
"""

import datetime
import re
import subprocess
import sys

SPECS = {
    "kmod-yeetmouse": "specs/kmod-yeetmouse.spec",
    "yeetmouse": "specs/yeetmouse.spec",
    "yeetmouse-gui": "specs/yeetmouse-gui.spec",
}

# Files whose change alters a package's build output, so the package needs a
# new version-release. .copr/Makefile generates every SRPM.
INPUTS = {
    "kmod-yeetmouse": {"specs/kmod-yeetmouse.spec", "config.h", ".copr/Makefile"},
    "yeetmouse": {"specs/yeetmouse.spec", "yeetmouse.service",
                  "yeetmouse-preset.conf", "yeetmouse-sysusers.conf",
                  "yeetmouse.conf", ".copr/Makefile"},
    "yeetmouse-gui": {"specs/yeetmouse-gui.spec", ".copr/Makefile"},
}

MIGRATION_HINT = ("manual timestamp-form migration required, see BUILDING.md "
                  "(\"Same-day upstream commits\")")

PATTERNS = {
    "commit": re.compile(
        r"^%global commit %\{\?commit\}%\{!\?commit:([0-9a-f]{40})\}$", re.M),
    "shortcommit": re.compile(
        r"^%global shortcommit %\{\?shortcommit\}%\{!\?shortcommit:([0-9a-f]{7,10})\}$",
        re.M),
    "snapdate": re.compile(r"^%global snapdate ([0-9]{8})$", re.M),
    "version": re.compile(r"^Version:[ \t]+(0\^%\{snapdate\}git%\{shortcommit\})$",
                          re.M),
    "release": re.compile(r"^Release:[ \t]+([1-9][0-9]*)%\{\?dist\}$", re.M),
}

# Any line that LOOKS like one of these fields, matched loosely, so a second
# or malformed copy is caught rather than ignored.
LOOSE = {
    "commit": re.compile(r"^\s*%global\s+commit\b", re.M),
    "shortcommit": re.compile(r"^\s*%global\s+shortcommit\b", re.M),
    "snapdate": re.compile(r"^\s*%global\s+snapdate\b", re.M),
    "version": re.compile(r"^\s*Version\s*:", re.M),
    "release": re.compile(r"^\s*Release\s*:", re.M),
}

# The one previous format, accepted only as a check-bump base.
LEGACY_PATTERNS = {
    "commit": PATTERNS["commit"],
    "shortcommit": re.compile(
        r"^%global shortcommit %\{\?shortcommit\}%\{!\?shortcommit:([0-9a-f]{7})\}$",
        re.M),
    "commitdate": re.compile(r"^%global commitdate ([0-9]{8})$", re.M),
    "pkgserial": re.compile(r"^%global pkgserial ([1-9][0-9]*)$", re.M),
    "version": re.compile(r"^Version:[ \t]+(0)$", re.M),
    "release": re.compile(
        r"^Release:[ \t]+(%\{pkgserial\}\.%\{commitdate\}git%\{shortcommit\}%\{\?dist\})$",
        re.M),
}
LEGACY_LOOSE = {
    "commit": LOOSE["commit"],
    "shortcommit": LOOSE["shortcommit"],
    "commitdate": re.compile(r"^\s*%global\s+commitdate\b", re.M),
    "pkgserial": re.compile(r"^\s*%global\s+pkgserial\b", re.M),
    "version": LOOSE["version"],
    "release": LOOSE["release"],
}


class SpecError(Exception):
    pass


def _valid_date(s):
    try:
        datetime.datetime.strptime(s, "%Y%m%d")
    except ValueError:
        return False
    return True


def _fields(text, where, patterns, loose):
    fields = {}
    for key, pat in patterns.items():
        strict = pat.findall(text)
        found = loose[key].findall(text)
        if len(strict) != 1 or len(found) != 1:
            raise SpecError(
                f"{where}: expected exactly one well-formed {key} line, found "
                f"{len(strict)} well-formed and {len(found)} total")
        fields[key] = strict[0]
    if not fields["commit"].startswith(fields["shortcommit"]):
        raise SpecError(f"{where}: shortcommit {fields['shortcommit']} is not "
                        f"a prefix of commit {fields['commit']}")
    return fields


def parse(text, where):
    """Parse the current format. Returns commit, shortcommit, snapdate,
    version (expanded), release (int)."""
    f = _fields(text, where, PATTERNS, LOOSE)
    if not _valid_date(f["snapdate"]):
        raise SpecError(f"{where}: snapdate {f['snapdate']} is not a valid date")
    f["release"] = int(f["release"])
    f["version"] = f"0^{f['snapdate']}git{f['shortcommit']}"
    return f


def parse_legacy(text, where):
    """Parse the one previous format (Version 0, pkgserial Release)."""
    f = _fields(text, where, LEGACY_PATTERNS, LEGACY_LOOSE)
    if not _valid_date(f["commitdate"]):
        raise SpecError(f"{where}: commitdate {f['commitdate']} is not a valid date")
    return f


def parse_or_exit(text, where):
    try:
        return parse(text, where)
    except SpecError as e:
        raise SystemExit(str(e))


def evr_of(fields):
    return f"{fields['version']}-{fields['release']}"


def compare(new, old):
    """Return (ok, reason). ok when NEW sorts strictly above OLD under rpm's
    rules for this format: a later snapdate wins, and for the same snapshot a
    higher Release wins. The same date with a different commit cannot be
    ordered, so it is never ok."""
    if new["snapdate"] > old["snapdate"]:
        return True, "newer snapshot"
    if new["snapdate"] < old["snapdate"]:
        return False, (f"snapshot date went backwards "
                       f"({old['snapdate']} -> {new['snapdate']})")
    if new["shortcommit"] != old["shortcommit"]:
        return False, (f"same snapshot date {new['snapdate']} with a different "
                       f"commit ({old['shortcommit']} -> {new['shortcommit']}): "
                       f"{MIGRATION_HINT}")
    if new["release"] > old["release"]:
        return True, "higher Release"
    return False, (f"Release stayed {old['release']} -> {new['release']} for "
                   f"the same snapshot")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def evr(path):
    print(evr_of(parse_or_exit(read(path), path)))
    return 0


def evrs():
    out = []
    for pkg, path in SPECS.items():
        out.append(f"{pkg}={evr_of(parse_or_exit(read(path), path))}")
    print(" ".join(out))
    return 0


def _pin(fields):
    return (fields["commit"], fields["shortcommit"], fields["snapdate"])


def bump_pin(sha, snapdate):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SystemExit(f"SHA must be 40 lowercase hex chars: {sha!r}")
    if not re.fullmatch(r"[0-9]{8}", snapdate) or not _valid_date(snapdate):
        raise SystemExit(f"SNAPDATE must be a valid YYYYMMDD date: {snapdate!r}")

    # Preflight: every spec parses and all three agree on the pin, before
    # anything is written.
    texts = {path: read(path) for path in SPECS.values()}
    olds = {path: parse_or_exit(text, path) for path, text in texts.items()}
    pins = {_pin(f) for f in olds.values()}
    if len(pins) != 1:
        raise SystemExit(f"the specs disagree on the pin, fix by hand first: "
                         f"{ {p: _pin(f) for p, f in olds.items()} }")
    cur_commit, cur_short, cur_date = pins.pop()
    if sha == cur_commit:
        print(f"already pinned to {sha}")
        return 0
    if snapdate <= cur_date:
        raise SystemExit(
            f"non-monotonic snapshot date (<= current): new commit {sha[:7]} "
            f"dated {snapdate}, current pin {cur_short} dated {cur_date}. "
            f"{MIGRATION_HINT}")

    short = sha[:7]
    subs = {
        "commit": f"%global commit %{{?commit}}%{{!?commit:{sha}}}",
        "shortcommit":
            f"%global shortcommit %{{?shortcommit}}%{{!?shortcommit:{short}}}",
        "snapdate": f"%global snapdate {snapdate}",
        "release": "Release:        1%{?dist}",
    }
    for path, text in texts.items():
        for key, line in subs.items():
            text = PATTERNS[key].sub(lambda _m, line=line: line, text)
        write(path, text)

    # Postflight: all three re-parse, agree, and carry Release 1.
    news = {path: parse_or_exit(read(path), path) for path in SPECS.values()}
    for path, new in news.items():
        if _pin(new) != (sha, short, snapdate) or new["release"] != 1:
            raise SystemExit(f"{path}: bump did not apply as expected: {new}")
        print(f"{path}: {evr_of(olds[path])} -> {evr_of(new)}")
    return 0


def bump_release(pkg):
    if pkg not in SPECS:
        raise SystemExit(f"unknown package {pkg!r}")
    path = SPECS[pkg]
    text = read(path)
    old = parse_or_exit(text, path)
    release = old["release"] + 1
    text = PATTERNS["release"].sub(
        lambda _m: f"Release:        {release}%{{?dist}}", text)
    write(path, text)
    new = parse_or_exit(read(path), path)
    rest = lambda f: {k: v for k, v in f.items() if k != "release"}  # noqa: E731
    if new["release"] != release or rest(new) != rest(old):
        raise SystemExit(f"{path}: Release bump did not apply as expected: {new}")
    print(f"{path}: {evr_of(old)} -> {evr_of(new)}")
    return 0


KMOD_SPEC = SPECS["kmod-yeetmouse"]

# A kernel NVR as dnf prints it for kernel-devel, for one Fedora release.
KERNEL_NVR = r"[0-9]+\.[0-9]+\.[0-9]+-[0-9a-z.]+\.fc{n}\.x86_64"
PIN_LINE = re.compile(r"^%global target_kernel_fc([0-9]+) (\S+)$", re.M)
PIN_LOOSE = re.compile(r"^\s*%global\s+target_kernel_", re.M)


def valid_kernel(n, nvr):
    return re.fullmatch(KERNEL_NVR.format(n=n), nvr) is not None


def kernel_pins(text, where):
    """{fedora release (int): kernel NVR} from the kmod spec. At least one
    pin must exist, each well-formed and for its own release, none repeated."""
    strict = PIN_LINE.findall(text)
    loose = PIN_LOOSE.findall(text)
    if not strict or len(strict) != len(loose):
        raise SystemExit(f"{where}: expected one or more well-formed "
                         f"'%global target_kernel_fcNN <NVR>' lines, found "
                         f"{len(strict)} well-formed and {len(loose)} total")
    pins = {}
    for n, nvr in strict:
        n = int(n)
        if n in pins:
            raise SystemExit(f"{where}: kernel pin for fc{n} appears twice")
        if not valid_kernel(n, nvr):
            raise SystemExit(f"{where}: kernel pin {nvr!r} is not an "
                             f"x86_64 kernel NVR for fc{n}")
        pins[n] = nvr
    return pins


def parse_pin_args(args):
    out = {}
    for arg in args:
        m = re.fullmatch(r"fc([0-9]+)=(\S+)", arg)
        if not m or not valid_kernel(int(m.group(1)), m.group(2)):
            raise SystemExit(f"bad fcNN=<kernel NVR> argument: {arg!r}")
        n = int(m.group(1))
        if n in out:
            raise SystemExit(f"fc{n} given twice")
        out[n] = m.group(2)
    return out


def rpmvercmp(a, b):
    """rpm's version-segment comparison (rpmvercmp), for the version or the
    release of a kernel NVR. Returns -1, 0 or 1. Tilde and caret do not occur
    in kernel NVRs, so they are not handled."""
    seg = re.compile(r"[0-9]+|[a-zA-Z]+")
    xa, xb = seg.findall(a), seg.findall(b)
    for sa, sb in zip(xa, xb):
        if sa.isdigit() != sb.isdigit():
            return 1 if sa.isdigit() else -1  # numeric segments sort higher
        if sa.isdigit():
            sa, sb = sa.lstrip("0") or "0", sb.lstrip("0") or "0"
            if len(sa) != len(sb):
                return 1 if len(sa) > len(sb) else -1
        if sa != sb:
            return 1 if sa > sb else -1
    return (len(xa) > len(xb)) - (len(xa) < len(xb))


def kernel_newer(new, old):
    """True if kernel NVR NEW sorts strictly above OLD (same release)."""
    nv, nr = new.split("-", 1)
    ov, orr = old.split("-", 1)
    c = rpmvercmp(nv, ov)
    return c > 0 or (c == 0 and rpmvercmp(nr, orr) > 0)


def set_kernels(args):
    only_newer = bool(args) and args[0] == "--only-newer"
    if only_newer:
        args = args[1:]
    want = parse_pin_args(args)
    text = read(KMOD_SPEC)
    old = kernel_pins(text, KMOD_SPEC)
    before = parse_or_exit(text, KMOD_SPEC)
    if only_newer:
        # A container can land on a mirror that is behind the one the last
        # run used. Never move a pin backwards, or two mirrors would make
        # the pin (and the kmod Release) flip back and forth.
        for n in [n for n in want if n in old and not kernel_newer(want[n], old[n])]:
            if want[n] != old[n]:
                print(f"fc{n}: keeping {old[n]}, {want[n]} is not newer")
            del want[n]
    changed = {n: nvr for n, nvr in want.items() if old.get(n) != nvr}
    if not changed:
        print("unchanged")
        return 0
    for n, nvr in changed.items():
        line = f"%global target_kernel_fc{n} {nvr}"
        if n in old:
            text = re.sub(rf"^%global target_kernel_fc{n} \S+$",
                          lambda _m, line=line: line, text, flags=re.M)
        else:
            # Insert after the last existing pin, keeping releases sorted.
            last = list(PIN_LINE.finditer(text))[-1]
            text = text[:last.end()] + "\n" + line + text[last.end():]
    lines = sorted((m.group(0) for m in PIN_LINE.finditer(text)),
                   key=lambda s: int(PIN_LINE.fullmatch(s).group(1)))
    first = next(PIN_LINE.finditer(text)).start()
    last = list(PIN_LINE.finditer(text))[-1].end()
    text = text[:first] + "\n".join(lines) + text[last:]
    write(KMOD_SPEC, text)

    # Postflight: the spec still parses, only the pins changed.
    new_text = read(KMOD_SPEC)
    after = parse_or_exit(new_text, KMOD_SPEC)
    new = kernel_pins(new_text, KMOD_SPEC)
    if after != before or new != {**old, **want}:
        raise SystemExit(f"{KMOD_SPEC}: kernel pin update did not apply as "
                         f"expected: {new}")
    for n in sorted(changed):
        print(f"fc{n}: {old.get(n, '(none)')} -> {changed[n]}")
    return 0


def _git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True,
                          text=True).stdout


SOURCE_LINE = re.compile(r"^(?:Source|Patch)[0-9]*:\s*(\S+)\s*$", re.M)

# The one remote source form these specs use: the upstream tarball, pinned by
# %{commit}. Any other value containing a macro is rejected below.
REMOTE_SOURCE = re.compile(
    r"%\{url\}/archive/%\{commit\}/YeetMouse-%\{commit\}\.tar\.gz")


def check_inputs_map(pkg, text, where):
    """Every local Source/Patch a spec declares must be listed in INPUTS, so
    a newly added file can never change a build without a version check."""
    missing = []
    for value in SOURCE_LINE.findall(text):
        if REMOTE_SOURCE.fullmatch(value) or (
                value.startswith("https://") and "%" not in value):
            # The pinned upstream tarball, or a literal URL. A literal URL
            # lives in the spec, so changing it is a spec change and is
            # covered by the version check.
            continue
        if "%" in value:
            raise SystemExit(f"{where}: local source {value!r} uses a macro; "
                             f"list it literally so the input map can see it")
        if value not in INPUTS[pkg]:
            missing.append(value)
    if missing:
        raise SystemExit(f"{where}: local sources {missing} are not in "
                         f"spec_version.py INPUTS[{pkg!r}]; add them")


def check_bump(base):
    changed = set(_git("diff", "--name-only", base, "--").split())
    # Untracked files are not part of a commit, so they are not considered.
    errors = []
    for pkg, inputs in INPUTS.items():
        touched = sorted(changed & inputs)
        spec = SPECS[pkg]
        # The working-tree spec must always be well-formed, touched or not.
        text = read(spec)
        new = parse_or_exit(text, spec)
        check_inputs_map(pkg, text, spec)
        if not touched:
            continue
        try:
            old_text = _git("show", f"{base}:{spec}")
        except subprocess.CalledProcessError:
            print(f"{pkg}: {spec} is new at this revision, no version check")
            continue
        where = f"{base}:{spec}"
        try:
            old = parse(old_text, where)
        except SpecError as current_err:
            try:
                parse_legacy(old_text, where)
            except SpecError as legacy_err:
                errors.append(f"{pkg}: cannot read the base spec in either "
                              f"format ({current_err}. {legacy_err})")
                continue
            # rpm sorts 0^<anything> above 0, whatever the old Release was.
            print(f"{pkg}: base uses the previous pkgserial format, "
                  f"{evr_of(new)} sorts above it")
            continue
        ok, reason = compare(new, old)
        if ok:
            print(f"{pkg}: {evr_of(old)} -> {evr_of(new)} ({reason}) for "
                  f"{', '.join(touched)}")
        else:
            errors.append(
                f"{pkg}: build inputs changed ({', '.join(touched)}) but the "
                f"version did not go up: {reason}. For a packaging-only change, "
                f"raise Release in {spec}. Otherwise the rebuild publishes a "
                f"version dnf will not update to.")
    for e in errors:
        print(f"::error::{e}")
    return 1 if errors else 0


def main(argv):
    if len(argv) == 2 and argv[1] == "kernel-pins":
        print(" ".join(f"fc{n}={nvr}" for n, nvr in
                       sorted(kernel_pins(read(KMOD_SPEC), KMOD_SPEC).items())))
        return 0
    if len(argv) >= 3 and argv[1] == "set-kernels":
        return set_kernels(argv[2:])
    if len(argv) == 3 and argv[1] == "evr":
        return evr(argv[2])
    if len(argv) == 2 and argv[1] == "evrs":
        return evrs()
    if len(argv) == 4 and argv[1] == "bump-pin":
        return bump_pin(argv[2], argv[3])
    if len(argv) == 3 and argv[1] == "bump-release":
        return bump_release(argv[2])
    if len(argv) == 3 and argv[1] == "check-bump":
        return check_bump(argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
