import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

ENV = {"COPR_URL": "https://copr.invalid", "COPR_OWNER": "o",
       "COPR_PROJECT": "p", "COPR_CHROOT": "fedora-44-x86_64"}

V = "0^20260803git78dcd0d"


def pkg(name, version, release, arch="x86_64"):
    return {"name": name, "version": version, "release": release, "arch": arch}


KMOD_BUILD = [
    pkg("yeetmouse-kmod", V, "1.fc44", "src"),
    pkg("yeetmouse-kmod-common", V, "1.fc44", "noarch"),
    pkg("kmod-yeetmouse-7.2.9-200.fc44.x86_64", V, "1.fc44"),
]


class Fake:
    """Stands in for COPR: builds per package, and built packages per id."""

    def __init__(self, cb, builds, packages):
        self.builds, self.packages = builds, packages
        cb._iter_builds = lambda package, status=None: [
            b for b in self.builds.get(package, [])
            if status is None or b["state"] == status]
        cb._built = lambda build_id: self.packages[build_id]


class MatchingTest(unittest.TestCase):
    def setUp(self):
        self.cb = helpers.load("copr_build", ENV)

    def ask(self, fn, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            fn(*args)
        return out.getvalue().strip()

    def fake(self, packages_by_build, package="kmod-yeetmouse"):
        Fake(self.cb, {package: [{"id": bid, "state": "succeeded"}
                                 for bid in packages_by_build]},
             packages_by_build)

    def test_parse_evr(self):
        w = self.cb.parse_evr(f"{V}-3")
        self.assertEqual((w["version"], w["release"], w["snapdate"], w["rel"]),
                         (V, "3", "20260803", 3))
        for bad in ("0-1", f"{V}", f"{V}-0", "0^2026083git78dcd0d-1",
                    "1^20260803git78dcd0d-1", "0-2.20260803git78dcd0d",
                    "0^20261332git78dcd0d-1"):
            with self.subTest(bad):
                with self.assertRaises(SystemExit):
                    self.cb.parse_evr(bad)

    def test_published_exact(self):
        self.fake({11: KMOD_BUILD})
        self.assertEqual(self.ask(self.cb.release_published, "kmod-yeetmouse", f"{V}-1"), "true")

    def test_wrong_version_or_release(self):
        self.fake({11: KMOD_BUILD})
        for evr in ("0^20260804git78dcd0d-1", f"{V}-2"):
            with self.subTest(evr):
                self.assertEqual(self.ask(self.cb.release_published, "kmod-yeetmouse", evr),
                                 "false")

    def test_src_record_alone_is_not_published(self):
        self.fake({11: [pkg("yeetmouse", V, "1.fc44", "src")]}, package="yeetmouse")
        self.assertEqual(self.ask(self.cb.release_published, "yeetmouse", f"{V}-1"), "false")

    def test_legacy_build_does_not_match(self):
        self.fake({11: [pkg("yeetmouse", "0", "1.20260803git78dcd0d.fc44")]},
                  package="yeetmouse")
        self.assertEqual(self.ask(self.cb.release_published, "yeetmouse", f"{V}-1"), "false")

    def test_other_dist_does_not_match(self):
        self.fake({11: [pkg("yeetmouse", V, "1.fc45")]}, package="yeetmouse")
        self.assertEqual(self.ask(self.cb.release_published, "yeetmouse", f"{V}-1"), "false")

    def test_has_kernel_build(self):
        self.fake({11: KMOD_BUILD})
        self.assertEqual(self.ask(self.cb.has_kernel_build, "7.2.9-200.fc44.x86_64", f"{V}-1"),
                         "true")
        self.assertEqual(self.ask(self.cb.has_kernel_build, "7.2.10-200.fc44.x86_64", f"{V}-1"),
                         "false")

    def test_common_package_never_satisfies_kernel_check(self):
        self.fake({11: [pkg("yeetmouse-kmod-common", V, "1.fc44", "noarch")]})
        self.assertEqual(self.ask(self.cb.has_kernel_build, "7.2.9-200.fc44.x86_64", f"{V}-1"),
                         "false")

    def test_failed_builds_ignored(self):
        Fake(self.cb, {"kmod-yeetmouse": [{"id": 11, "state": "failed"}]}, {11: KMOD_BUILD})
        self.assertEqual(self.ask(self.cb.release_published, "kmod-yeetmouse", f"{V}-1"), "false")

    def test_newer_release_detection(self):
        want = self.cb.parse_evr(f"{V}-1")
        self.cb._built = lambda bid: {
            1: [pkg("yeetmouse", V, "2.fc44")],
            2: [pkg("yeetmouse", "0^20260804gitaaaaaaa", "1.fc44")],
            3: [pkg("yeetmouse", "0^20260803gitc3d12f3", "5.fc44")],
            4: [pkg("yeetmouse", V, "2.fc44", "src")],
            5: [pkg("yeetmouse", "0", "9.20260803git78dcd0d.fc44")],
        }[bid]
        self.assertEqual(self.cb._newer_release_from([1], want), f"{V}-2.fc44")
        self.assertEqual(self.cb._newer_release_from([2], want), "0^20260804gitaaaaaaa-1.fc44")
        for bid in (3, 4, 5):
            with self.subTest(bid):
                self.assertIsNone(self.cb._newer_release_from([bid], want))


class EnsureBuiltTest(unittest.TestCase):
    """ensure_built's control flow with COPR replaced by fakes."""

    def setUp(self):
        self.cb = helpers.load("copr_build", ENV)
        self.want = {"yeetmouse": self.cb.parse_evr(f"{V}-1")}
        self.published = set()   # packages that count as published
        self.in_flight = []      # build ids already running
        self.submits = []        # packages submitted
        self.final_state = "succeeded"
        self.on_success = None   # callable run when a wait sees success
        self.built = {}
        cb = self.cb
        cb._find_published = lambda p, w, name=None: 99 if p in self.published else 0
        cb._in_flight = lambda p: list(self.in_flight)
        cb._built = lambda bid: self.built.get(bid, [])

        def submit(p):
            self.submits.append(p)
            return [500 + len(self.submits)], False
        cb._submit = submit

        def wait(builds):
            if self.final_state == "succeeded" and self.on_success:
                self.on_success()
            return {b: self.final_state for b in builds}
        cb._wait = wait

    def run_it(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = self.cb.ensure_built(self.want)
        return rc, out.getvalue()

    def test_already_published_submits_nothing(self):
        self.published.add("yeetmouse")
        rc, out = self.run_it()
        self.assertEqual((rc, self.submits), (0, []))
        self.assertIn("already published", out)

    def test_submits_once_and_succeeds(self):
        self.on_success = lambda: self.published.add("yeetmouse")
        rc, _ = self.run_it()
        self.assertEqual((rc, self.submits), (0, ["yeetmouse"]))

    def test_in_flight_build_is_waited_for_not_duplicated(self):
        self.in_flight = [400]
        self.on_success = lambda: self.published.add("yeetmouse")
        rc, out = self.run_it()
        self.assertEqual((rc, self.submits), (0, []))
        self.assertIn("waiting for in-flight build 400", out)

    def test_failed_build_reports_error(self):
        self.final_state = "failed"
        rc, out = self.run_it()
        self.assertEqual((rc, self.submits), (1, ["yeetmouse"]))
        self.assertIn(f"::error::yeetmouse: {V}-1 not published", out)

    def test_timeout_reports_still_running(self):
        self.final_state = "running"
        rc, out = self.run_it()
        self.assertEqual(rc, 1)
        self.assertIn("still running", out)

    def test_success_that_published_something_else_is_an_error(self):
        self.built = {501: [pkg("yeetmouse", V, "1.fc44", "src")]}
        rc, out = self.run_it()
        self.assertEqual(rc, 1)
        self.assertIn("although the build succeeded", out)

    def test_newer_main_revision_counts(self):
        self.built = {501: [pkg("yeetmouse", "0^20260804gitaaaaaaa", "1.fc44")]}
        rc, out = self.run_it()
        self.assertEqual(rc, 0, out)
        self.assertIn("a newer main revision was built", out)

    def test_bad_pair_argument(self):
        for arg in ("yeetmouse", "yeetmouse=", "=0^20260803git78dcd0d-1", "yeetmouse=0-1"):
            with self.subTest(arg):
                with self.assertRaises(SystemExit):
                    self.cb._pairs([arg])


class ChrootTest(unittest.TestCase):
    def test_unsupported_chroot_fails_closed(self):
        for chroot in ("epel-9-x86_64", "fedora-rawhide-x86_64", "fedora-44-aarch64"):
            with self.subTest(chroot):
                cb = helpers.load("copr_build", dict(ENV, COPR_CHROOT=chroot))
                with self.assertRaises(SystemExit):
                    cb._dist()

    def test_dist_from_chroot(self):
        cb = helpers.load("copr_build", dict(ENV, COPR_CHROOT="fedora-45-x86_64"))
        self.assertEqual(cb._dist(), "fc45")


if __name__ == "__main__":
    unittest.main()
