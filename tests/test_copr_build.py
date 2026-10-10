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
                    "1^20260803git78dcd0d-1", "0-2.20260803git78dcd0d"):
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
