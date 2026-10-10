import contextlib
import io
import os
import re
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

sv = helpers.load("spec_version")

CUR_SHA = "78dcd0d573bedd5dd7b9e29e9162b28c9eb2fd7b"
NEW_SHA = "c3d12f3313a95f25162a1503be624f3b0617f8c0"

LEGACY_SPEC = """\
%global commit %{?commit}%{!?commit:78dcd0d573bedd5dd7b9e29e9162b28c9eb2fd7b}
%global shortcommit %{?shortcommit}%{!?shortcommit:78dcd0d}
%global commitdate 20260803
%global pkgserial 2
Name: x
Version:        0
Release:        %{pkgserial}.%{commitdate}git%{shortcommit}%{?dist}
"""


class InRepo(unittest.TestCase):
    """Each test runs in a throwaway copy of the repository."""

    def setUp(self):
        self.d = helpers.copy_repo()
        self.cwd = os.getcwd()
        os.chdir(self.d)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.d)

    def run_cmd(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                rc = sv.main(["spec_version.py", *argv])
            except SystemExit as e:
                return (e.code if isinstance(e.code, int) else 1), \
                    out.getvalue() + str(e)
        return rc, out.getvalue()

    def spec(self, pkg):
        return helpers.read(self.d, sv.SPECS[pkg])

    def set_spec(self, pkg, text):
        helpers.write(self.d, sv.SPECS[pkg], text)


class ParseTest(InRepo):
    def test_current_specs_parse(self):
        for pkg in sv.SPECS:
            f = sv.parse(self.spec(pkg), pkg)
            self.assertEqual(f["version"], "0^20260803git78dcd0d")
            self.assertEqual(f["release"], 1)

    def test_evrs(self):
        rc, out = self.run_cmd("evrs")
        self.assertEqual(rc, 0)
        self.assertEqual(out.split(), [
            "kmod-yeetmouse=0^20260803git78dcd0d-1",
            "yeetmouse=0^20260803git78dcd0d-1",
            "yeetmouse-gui=0^20260803git78dcd0d-1"])

    def test_rejects_malformed(self):
        base = self.spec("yeetmouse")
        bad = {
            "duplicate snapdate": base.replace(
                "%global snapdate 20260803", "%global snapdate 20260803\n%global snapdate 20260804"),
            "9-digit snapdate": base.replace("snapdate 20260803", "snapdate 202608031"),
            "invalid date": base.replace("snapdate 20260803", "snapdate 20261332"),
            "release macro": base.replace("Release:        1%{?dist}",
                                          "Release:        %{rel}%{?dist}"),
            "release zero": base.replace("Release:        1%{?dist}", "Release:        0%{?dist}"),
            "version literal": base.replace("Version:        0^%{snapdate}git%{shortcommit}",
                                            "Version:        0^20260803git78dcd0d"),
            "short not prefix": base.replace("!?shortcommit:78dcd0d", "!?shortcommit:1234567"),
        }
        for name, text in bad.items():
            with self.subTest(name):
                with self.assertRaises(sv.SpecError):
                    sv.parse(text, name)

    def test_legacy_parser(self):
        f = sv.parse_legacy(LEGACY_SPEC, "legacy")
        self.assertEqual(f["pkgserial"], "2")
        with self.assertRaises(sv.SpecError):
            sv.parse_legacy(LEGACY_SPEC.replace("%global pkgserial 2\n", ""), "x")
        with self.assertRaises(sv.SpecError):
            sv.parse(LEGACY_SPEC, "legacy is not current")


class BumpPinTest(InRepo):
    def test_newer_date_sets_pin_and_resets_release(self):
        self.set_spec("kmod-yeetmouse", self.spec("kmod-yeetmouse").replace(
            "Release:        1%{?dist}", "Release:        4%{?dist}"))
        rc, _ = self.run_cmd("bump-pin", NEW_SHA, "20261009")
        self.assertEqual(rc, 0)
        for pkg in sv.SPECS:
            f = sv.parse(self.spec(pkg), pkg)
            self.assertEqual((f["commit"], f["shortcommit"], f["snapdate"], f["release"]),
                             (NEW_SHA, "c3d12f3", "20261009", 1))

    def test_equal_sha_is_noop(self):
        before = {p: self.spec(p) for p in sv.SPECS}
        rc, out = self.run_cmd("bump-pin", CUR_SHA, "20261009")
        self.assertEqual(rc, 0)
        self.assertIn("already pinned", out)
        self.assertEqual(before, {p: self.spec(p) for p in sv.SPECS})

    def test_same_or_older_date_refused_without_writes(self):
        before = {p: self.spec(p) for p in sv.SPECS}
        for date in ("20260803", "20260802"):
            with self.subTest(date):
                rc, out = self.run_cmd("bump-pin", NEW_SHA, date)
                self.assertNotEqual(rc, 0)
                self.assertIn("non-monotonic snapshot date (<= current)", out)
                self.assertIn("manual timestamp-form migration required", out)
                self.assertEqual(before, {p: self.spec(p) for p in sv.SPECS})

    def test_disagreeing_specs_refused_without_writes(self):
        self.set_spec("yeetmouse-gui", self.spec("yeetmouse-gui").replace(
            "snapdate 20260803", "snapdate 20260801"))
        before = {p: self.spec(p) for p in sv.SPECS}
        rc, out = self.run_cmd("bump-pin", NEW_SHA, "20261009")
        self.assertNotEqual(rc, 0)
        self.assertIn("disagree", out)
        self.assertEqual(before, {p: self.spec(p) for p in sv.SPECS})

    def test_bad_arguments(self):
        for sha, date in ((NEW_SHA[:39], "20261009"), (NEW_SHA, "2026109"),
                          (NEW_SHA, "20261340")):
            with self.subTest((sha, date)):
                rc, _ = self.run_cmd("bump-pin", sha, date)
                self.assertNotEqual(rc, 0)


class BumpReleaseTest(InRepo):
    def test_only_release_changes(self):
        before = sv.parse(self.spec("kmod-yeetmouse"), "k")
        rc, _ = self.run_cmd("bump-release", "kmod-yeetmouse")
        self.assertEqual(rc, 0)
        after = sv.parse(self.spec("kmod-yeetmouse"), "k")
        self.assertEqual(after["release"], before["release"] + 1)
        self.assertEqual({k: v for k, v in after.items() if k != "release"},
                         {k: v for k, v in before.items() if k != "release"})
        self.assertEqual(sv.parse(self.spec("yeetmouse"), "y")["release"], 1)


class CheckBumpTest(InRepo):
    def commit(self, msg="change"):
        helpers.git(self.d, "add", "-A")
        helpers.git(self.d, "commit", "-q", "-m", msg)

    def base(self):
        return helpers.git(self.d, "rev-parse", "HEAD").strip()

    def test_docs_only_passes(self):
        b = self.base()
        helpers.write(self.d, "README.md", "docs\n")
        self.assertEqual(self.run_cmd("check-bump", b)[0], 0)

    def test_input_change_without_bump_fails(self):
        b = self.base()
        helpers.write(self.d, "config.h", helpers.read(self.d, "config.h") + "\n")
        rc, out = self.run_cmd("check-bump", b)
        self.assertEqual(rc, 1)
        self.assertIn("kmod-yeetmouse", out)

    def test_input_change_with_release_bump_passes(self):
        b = self.base()
        helpers.write(self.d, "config.h", helpers.read(self.d, "config.h") + "\n")
        self.run_cmd("bump-release", "kmod-yeetmouse")
        self.assertEqual(self.run_cmd("check-bump", b)[0], 0)

    def test_new_snapshot_passes(self):
        b = self.base()
        self.run_cmd("bump-pin", NEW_SHA, "20261009")
        self.assertEqual(self.run_cmd("check-bump", b)[0], 0)

    def test_same_date_different_commit_fails(self):
        b = self.base()
        for pkg in sv.SPECS:
            t = self.spec(pkg).replace(CUR_SHA, NEW_SHA).replace(
                "!?shortcommit:78dcd0d", "!?shortcommit:c3d12f3")
            self.set_spec(pkg, t)
        rc, out = self.run_cmd("check-bump", b)
        self.assertEqual(rc, 1)
        self.assertIn("same snapshot date", out)

    def test_older_date_fails_even_with_higher_release(self):
        b = self.base()
        t = self.spec("yeetmouse").replace("snapdate 20260803", "snapdate 20260801").replace(
            "Release:        1%{?dist}", "Release:        9%{?dist}")
        self.set_spec("yeetmouse", t)
        rc, out = self.run_cmd("check-bump", b)
        self.assertEqual(rc, 1)
        self.assertIn("went backwards", out)

    def test_legacy_base_is_lower(self):
        # Make the base commit hold the previous format for every spec.
        current = {p: self.spec(p) for p in sv.SPECS}
        for pkg in sv.SPECS:
            self.set_spec(pkg, LEGACY_SPEC)
        self.commit("legacy base")
        b = self.base()
        for pkg, text in current.items():
            self.set_spec(pkg, text)
        rc, out = self.run_cmd("check-bump", b)
        self.assertEqual(rc, 0, out)
        self.assertIn("previous pkgserial format", out)

    def test_unknown_base_format_fails(self):
        current = self.spec("yeetmouse")
        self.set_spec("yeetmouse", LEGACY_SPEC.replace("%global pkgserial 2\n", ""))
        self.commit("broken base")
        b = self.base()
        self.set_spec("yeetmouse", current)
        rc, out = self.run_cmd("check-bump", b)
        self.assertEqual(rc, 1)
        self.assertIn("cannot read the base spec", out)


class CompareTest(unittest.TestCase):
    def f(self, date, short, rel):
        return {"snapdate": date, "shortcommit": short, "release": rel}

    def test_rules(self):
        cases = [
            (self.f("20260804", "aaaaaaa", 1), self.f("20260803", "78dcd0d", 9), True),
            (self.f("20260803", "78dcd0d", 2), self.f("20260803", "78dcd0d", 1), True),
            (self.f("20260803", "78dcd0d", 1), self.f("20260803", "78dcd0d", 1), False),
            (self.f("20260803", "c3d12f3", 5), self.f("20260803", "78dcd0d", 1), False),
            (self.f("20260802", "c3d12f3", 9), self.f("20260803", "78dcd0d", 1), False),
        ]
        for new, old, want in cases:
            with self.subTest((new, old)):
                self.assertEqual(sv.compare(new, old)[0], want)

    def test_matches_rpm_where_available(self):
        """Cross-check compare() against rpm's own ordering when the rpm
        Python bindings exist (Fedora toolbox); skipped on the CI runner."""
        try:
            import rpm
        except ImportError:
            self.skipTest("rpm bindings not installed")
        pairs = [(("20260804", "aaaaaaa", 1), ("20260803", "78dcd0d", 9)),
                 (("20260803", "78dcd0d", 2), ("20260803", "78dcd0d", 1)),
                 (("20260802", "c3d12f3", 9), ("20260803", "78dcd0d", 1))]
        for (nd, ns, nr), (od, os_, orl) in pairs:
            ok = sv.compare(self.f(nd, ns, nr), self.f(od, os_, orl))[0]
            r = rpm.labelCompare(("0", f"0^{nd}git{ns}", str(nr)),
                                 ("0", f"0^{od}git{os_}", str(orl)))
            self.assertEqual(ok, r > 0)
        self.assertGreater(rpm.labelCompare(("0", "0^20260803git78dcd0d", "1"),
                                            ("0", "0", "99.20260803git78dcd0d")), 0)


if __name__ == "__main__":
    unittest.main()
