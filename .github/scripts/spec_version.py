#!/usr/bin/env python3
"""Read, bump and check the version fields of this repo's three specs.

Every spec carries exactly one of each of these lines:

  %global commit %{?commit}%{!?commit:<40-hex upstream sha>}
  %global shortcommit %{?shortcommit}%{!?shortcommit:<7-hex>}
  %global commitdate <YYYYMMDD>
  %global pkgserial <positive integer>
  Version:        0
  Release:        %{pkgserial}.%{commitdate}git%{shortcommit}%{?dist}

pkgserial alone decides the order of builds (it comes first in Release and
only ever goes up). commitdate and shortcommit are informational.

Subcommands:
  release-prefix SPEC
      Print "<pkgserial>.<commitdate>git<shortcommit>", the Release value
      without the dist tag.

  release-prefixes
      Print "PACKAGE=PREFIX" for all three packages, space-separated.

  bump-pin SHA COMMITDATE
      In all three specs: set the commit pin to SHA, commitdate to COMMITDATE
      and add 1 to pkgserial. Every edit is verified by re-reading the file.

  bump-serial PACKAGE
      Add 1 to PACKAGE's pkgserial only. Used by the kernel poller, so a
      kernel-only rebuild never republishes yeetmouse-kmod-common (noarch,
      same NEVR for every kernel) at an already-published release.

  check-bump BASE_REF
      For every package whose build inputs changed between BASE_REF and the
      working tree, require its pkgserial to be strictly greater than at
      BASE_REF. Exit 1 listing every violation. A spec that does not exist at
      BASE_REF is exempt (a new package).
"""

import re
import subprocess
import sys

SPECS = {
    "kmod-yeetmouse": "specs/kmod-yeetmouse.spec",
    "yeetmouse": "specs/yeetmouse.spec",
    "yeetmouse-gui": "specs/yeetmouse-gui.spec",
}

# Files whose change alters a package's build output, so the package needs a
# new serial. .copr/Makefile generates every SRPM.
INPUTS = {
    "kmod-yeetmouse": {"specs/kmod-yeetmouse.spec", "config.h", ".copr/Makefile"},
    "yeetmouse": {"specs/yeetmouse.spec", "yeetmouse.service",
                  "yeetmouse-preset.conf", "yeetmouse-sysusers.conf",
                  "yeetmouse.conf", ".copr/Makefile"},
    "yeetmouse-gui": {"specs/yeetmouse-gui.spec", ".copr/Makefile"},
}

PATTERNS = {
    "commit": re.compile(
        r"^%global commit %\{\?commit\}%\{!\?commit:([0-9a-f]{40})\}$", re.M),
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

# Any line that LOOKS like one of these fields, matched loosely, so a second
# or malformed copy is caught rather than ignored.
LOOSE = {
    "commit": re.compile(r"^\s*%global\s+commit\b", re.M),
    "shortcommit": re.compile(r"^\s*%global\s+shortcommit\b", re.M),
    "commitdate": re.compile(r"^\s*%global\s+commitdate\b", re.M),
    "pkgserial": re.compile(r"^\s*%global\s+pkgserial\b", re.M),
    "version": re.compile(r"^\s*Version\s*:", re.M),
    "release": re.compile(r"^\s*Release\s*:", re.M),
}


def parse(text, where):
    fields = {}
    for key, pat in PATTERNS.items():
        strict = pat.findall(text)
        loose = LOOSE[key].findall(text)
        if len(strict) != 1 or len(loose) != 1:
            raise SystemExit(
                f"{where}: expected exactly one well-formed {key} line, found "
                f"{len(strict)} well-formed and {len(loose)} total")
        fields[key] = strict[0]
    if not fields["commit"].startswith(fields["shortcommit"]):
        raise SystemExit(f"{where}: shortcommit {fields['shortcommit']} is not "
                         f"a prefix of commit {fields['commit']}")
    fields["pkgserial"] = int(fields["pkgserial"])
    return fields


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def release_prefix(path):
    f = parse(read(path), path)
    print(f"{f['pkgserial']}.{f['commitdate']}git{f['shortcommit']}")
    return 0


def release_prefixes():
    """Print "PACKAGE=PREFIX" for every package, space-separated, for
    copr_build.py ensure-built."""
    out = []
    for pkg, path in SPECS.items():
        f = parse(read(path), path)
        out.append(f"{pkg}={f['pkgserial']}.{f['commitdate']}git{f['shortcommit']}")
    print(" ".join(out))
    return 0


def bump_pin(sha, commitdate):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise SystemExit(f"SHA must be 40 lowercase hex chars: {sha!r}")
    if not re.fullmatch(r"[0-9]{8}", commitdate):
        raise SystemExit(f"COMMITDATE must be YYYYMMDD: {commitdate!r}")
    short = sha[:7]
    for path in SPECS.values():
        text = read(path)
        old = parse(text, path)
        serial = old["pkgserial"] + 1
        subs = {
            "commit": f"%global commit %{{?commit}}%{{!?commit:{sha}}}",
            "shortcommit":
                f"%global shortcommit %{{?shortcommit}}%{{!?shortcommit:{short}}}",
            "commitdate": f"%global commitdate {commitdate}",
            "pkgserial": f"%global pkgserial {serial}",
        }
        for key, line in subs.items():
            text = PATTERNS[key].sub(lambda _m, line=line: line, text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        new = parse(read(path), path)
        if (new["commit"], new["shortcommit"], new["commitdate"],
                new["pkgserial"]) != (sha, short, commitdate, serial):
            raise SystemExit(f"{path}: bump did not apply as expected: {new}")
        print(f"{path}: serial {old['pkgserial']} -> {serial}, "
              f"pin {old['shortcommit']} -> {short}, date {commitdate}")
    return 0


def bump_serial(pkg):
    if pkg not in SPECS:
        raise SystemExit(f"unknown package {pkg!r}")
    path = SPECS[pkg]
    text = read(path)
    old = parse(text, path)
    serial = old["pkgserial"] + 1
    text = PATTERNS["pkgserial"].sub(f"%global pkgserial {serial}", text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    new = parse(read(path), path)
    if new["pkgserial"] != serial or {k: v for k, v in new.items()
                                      if k != "pkgserial"} != \
            {k: v for k, v in old.items() if k != "pkgserial"}:
        raise SystemExit(f"{path}: serial bump did not apply as expected: {new}")
    print(f"{path}: serial {old['pkgserial']} -> {serial}")
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
    a newly added file can never change a build without a serial check."""
    missing = []
    for value in SOURCE_LINE.findall(text):
        if REMOTE_SOURCE.fullmatch(value) or (
                value.startswith("https://") and "%" not in value):
            # The pinned upstream tarball, or a literal URL. A literal URL
            # lives in the spec, so changing it is a spec change and is
            # covered by the serial check.
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
        new = parse(text, spec)
        check_inputs_map(pkg, text, spec)
        if not touched:
            continue
        try:
            old_text = _git("show", f"{base}:{spec}")
        except subprocess.CalledProcessError:
            print(f"{pkg}: {spec} is new at this revision, no serial check")
            continue
        if not LOOSE["pkgserial"].search(old_text):
            # One-time transition: the base predates pkgserial entirely, so
            # there is nothing to compare against. A base that HAS a
            # pkgserial line but a malformed one still fails parse() below.
            print(f"{pkg}: {spec} introduces pkgserial at this revision, "
                  f"no serial check")
            continue
        old = parse(old_text, f"{base}:{spec}")
        if new["pkgserial"] <= old["pkgserial"]:
            errors.append(
                f"{pkg}: build inputs changed ({', '.join(touched)}) but "
                f"pkgserial stayed {old['pkgserial']} -> {new['pkgserial']}. "
                f"Increase %global pkgserial in {spec}, otherwise the rebuild "
                f"publishes the same version and dnf will not update to it.")
        else:
            print(f"{pkg}: pkgserial {old['pkgserial']} -> {new['pkgserial']} "
                  f"for {', '.join(touched)}")
    for e in errors:
        print(f"::error::{e}")
    return 1 if errors else 0


def main(argv):
    if len(argv) == 3 and argv[1] == "release-prefix":
        return release_prefix(argv[2])
    if len(argv) == 4 and argv[1] == "bump-pin":
        return bump_pin(argv[2], argv[3])
    if len(argv) == 2 and argv[1] == "release-prefixes":
        return release_prefixes()
    if len(argv) == 3 and argv[1] == "bump-serial":
        return bump_serial(argv[2])
    if len(argv) == 3 and argv[1] == "check-bump":
        return check_bump(argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
