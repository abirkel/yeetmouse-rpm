import contextlib
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

ENV = {"COPR_URL": "https://copr.invalid", "COPR_OWNER": "o",
       "COPR_PROJECT": "p"}

V = "0^20260803git78dcd0d"
F44, F45, RAW = "fedora-44-x86_64", "fedora-45-x86_64", "fedora-rawhide-x86_64"
K44 = "7.2.9-201.fc44.x86_64"
PINS = {44: K44, 45: "7.2.9-301.fc45.x86_64"}


def pkg(name, version, release, arch="x86_64"):
    return {"name": name, "version": version, "release": release, "arch": arch}


def kmod_build(rel="1", dist="fc44", kernel=K44):
    return [
        pkg("yeetmouse-kmod", V, f"{rel}.{dist}", "src"),
        pkg("yeetmouse-kmod-common", V, f"{rel}.{dist}", "noarch"),
        pkg(f"kmod-yeetmouse-{kernel}", V, f"{rel}.{dist}"),
    ]


def quiet(fn, *args, **kw):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        rc = fn(*args, **kw)
    return rc, out.getvalue()


class Fake:
    """Stands in for COPR. builds: {package: [build dicts]}, each with id,
    state and chroots. packages: {(build id, chroot): [built packages]}.
    chroot_states: {(build id, chroot): state} for multi-chroot builds."""

    def __init__(self, cb, builds, packages, chroot_states=None):
        self.builds, self.packages = builds, packages
        self.chroot_states = chroot_states or {}
        cb._iter_builds = lambda package: list(self.builds.get(package, []))
        cb._built = lambda bid, chroot: self.packages.get((bid, chroot), [])
        orig = cb._chroot_state

        def state(build, chroot):
            key = (build["id"], chroot)
            if key in self.chroot_states:
                return self.chroot_states[key]
            return orig(build, chroot)
        cb._chroot_state = state


class MatchingTest(unittest.TestCase):
    def setUp(self):
        self.cb = helpers.load("copr_build", ENV)

    def ask(self, fn, *args):
        return quiet(fn, *args)[1].strip()

    def one(self, packages, package="kmod-yeetmouse", chroot=F44, state="succeeded"):
        Fake(self.cb, {package: [{"id": 11, "state": state, "chroots": [chroot]}]},
             {(11, chroot): packages})

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

    def test_published_exact_in_its_chroot_only(self):
        self.one(kmod_build())
        self.assertEqual(self.ask(self.cb.release_published, "kmod-yeetmouse", f"{V}-1", F44),
                         "true")
        self.assertEqual(self.ask(self.cb.release_published, "kmod-yeetmouse", f"{V}-1", F45),
                         "false")

    def test_wrong_version_or_release(self):
        self.one(kmod_build())
        for evr in ("0^20260804git78dcd0d-1", f"{V}-2"):
            with self.subTest(evr):
                self.assertEqual(
                    self.ask(self.cb.release_published, "kmod-yeetmouse", evr, F44), "false")

    def test_src_record_alone_is_not_published(self):
        self.one([pkg("yeetmouse", V, "1.fc44", "src")], package="yeetmouse")
        self.assertEqual(self.ask(self.cb.release_published, "yeetmouse", f"{V}-1", F44),
                         "false")

    def test_other_dist_does_not_match(self):
        self.one([pkg("yeetmouse", V, "1.fc45")], package="yeetmouse")
        self.assertEqual(self.ask(self.cb.release_published, "yeetmouse", f"{V}-1", F44),
                         "false")

    def test_has_kernel_build(self):
        self.one(kmod_build())
        self.assertEqual(self.ask(self.cb.has_kernel_build, K44, f"{V}-1", F44), "true")
        self.assertEqual(self.ask(self.cb.has_kernel_build, "7.2.10-200.fc44.x86_64",
                                  f"{V}-1", F44), "false")

    def test_common_package_never_satisfies_kernel_check(self):
        self.one([pkg("yeetmouse-kmod-common", V, "1.fc44", "noarch")])
        self.assertEqual(self.ask(self.cb.has_kernel_build, K44, f"{V}-1", F44), "false")

    def test_failed_build_never_counts(self):
        self.one(kmod_build(), state="failed")
        self.assertEqual(self.ask(self.cb.release_published, "kmod-yeetmouse", f"{V}-1", F44),
                         "false")

    def test_multi_chroot_build_is_read_per_chroot(self):
        # A manual build for both chroots: failed overall, succeeded in F44.
        Fake(self.cb,
             {"yeetmouse": [{"id": 11, "state": "failed", "chroots": [F44, F45]}]},
             {(11, F44): [pkg("yeetmouse", V, "1.fc44")],
              (11, F45): [pkg("yeetmouse", V, "1.fc45")]},
             chroot_states={(11, F44): "succeeded", (11, F45): "failed"})
        self.assertEqual(self.ask(self.cb.release_published, "yeetmouse", f"{V}-1", F44),
                         "true")
        self.assertEqual(self.ask(self.cb.release_published, "yeetmouse", f"{V}-1", F45),
                         "false")

    def test_newer_release_detection(self):
        want = self.cb.parse_evr(f"{V}-1")
        table = {
            1: [pkg("yeetmouse", V, "2.fc44")],
            2: [pkg("yeetmouse", "0^20260804gitaaaaaaa", "1.fc44")],
            3: [pkg("yeetmouse", "0^20260803gitc3d12f3", "5.fc44")],
            4: [pkg("yeetmouse", V, "2.fc44", "src")],
            5: [pkg("yeetmouse", "0", "9.20260803git78dcd0d.fc44")],
            6: [pkg("yeetmouse", V, "2.fc45")],
        }
        self.cb._built = lambda bid, chroot: table[bid]
        self.assertEqual(self.cb._newer_release_from([1], want, F44), f"{V}-2.fc44")
        self.assertEqual(self.cb._newer_release_from([2], want, F44),
                         "0^20260804gitaaaaaaa-1.fc44")
        for bid in (3, 4, 5, 6):
            with self.subTest(bid):
                self.assertIsNone(self.cb._newer_release_from([bid], want, F44))


class SubmitTest(unittest.TestCase):
    def test_submission_always_names_one_chroot(self):
        cb = helpers.load("copr_build", ENV)
        posted = []
        cb._latest_id = lambda package: 10
        cb._post = lambda path, body: posted.append((path, body)) or {"id": 11}
        self.assertEqual(cb._submit("yeetmouse", F45), ([11], False))
        self.assertEqual(posted, [("package/build", {
            "ownername": "o", "projectname": "p", "package_name": "yeetmouse",
            "chroots": [F45]})])


class EnsureBuiltTest(unittest.TestCase):
    """ensure_built's control flow with COPR replaced by fakes."""

    def setUp(self):
        self.cb = helpers.load("copr_build", ENV)
        self.want = {"yeetmouse": self.cb.parse_evr(f"{V}-1")}
        self.published = set()   # (package, chroot) keys that count as published
        self.conflicts = {}      # key -> conflict message
        self.in_flight = {}      # key -> build ids already running
        self.submits = []        # keys submitted
        self.final_state = "succeeded"
        self.on_success = None   # callable run when a wait sees success
        self.built = {}
        self.age = None
        cb = self.cb
        cb._published = lambda key, want, pins: (
            (99 if key in self.published else 0), self.conflicts.get(key))
        cb._in_flight = lambda p, c: list(self.in_flight.get((p, c), []))
        cb._built = lambda bid, chroot: self.built.get(bid, [])
        cb._spec_age_hours = lambda p: self.age

        def submit(p, c):
            self.submits.append((p, c))
            return [500 + len(self.submits)], False
        cb._submit = submit

        def wait(builds):
            if self.final_state == "succeeded" and self.on_success:
                self.on_success(builds)
            return {b: self.final_state for b in builds}
        cb._wait = wait

    def run_it(self, chroots=(F44,), grace=0.0):
        return quiet(self.cb.ensure_built, list(chroots), self.want, grace, pins=PINS)

    def publish_all(self, builds):
        self.published.update(builds.values())

    def test_already_published_submits_nothing(self):
        self.published.add(("yeetmouse", F44))
        rc, out = self.run_it()
        self.assertEqual((rc, self.submits), (0, []))
        self.assertIn("already published", out)

    def test_only_missing_chroot_is_built(self):
        self.published.add(("yeetmouse", F44))
        self.on_success = self.publish_all
        rc, _ = self.run_it(chroots=(F44, F45))
        self.assertEqual((rc, self.submits), (0, [("yeetmouse", F45)]))

    def test_submits_once_per_chroot_and_succeeds(self):
        self.on_success = self.publish_all
        rc, _ = self.run_it(chroots=(F44, F45))
        self.assertEqual((rc, self.submits), (0, [("yeetmouse", F44), ("yeetmouse", F45)]))

    def test_in_flight_build_is_waited_for_not_duplicated(self):
        self.in_flight = {("yeetmouse", F44): [400]}
        self.on_success = self.publish_all
        rc, out = self.run_it()
        self.assertEqual((rc, self.submits), (0, []))
        self.assertIn("waiting for in-flight build 400", out)

    def test_failed_build_reports_error(self):
        self.final_state = "failed"
        rc, out = self.run_it()
        self.assertEqual((rc, self.submits), (1, [("yeetmouse", F44)]))
        self.assertIn(f"::error::yeetmouse {F44}: {V}-1 not published", out)

    def test_failure_within_grace_is_a_warning(self):
        self.final_state = "failed"
        self.age = 3.0
        rc, out = self.run_it(grace=24)
        self.assertEqual(rc, 0, out)
        self.assertIn("::warning::yeetmouse", out)

    def test_failure_after_grace_is_an_error(self):
        self.final_state = "failed"
        self.age = 30.0
        rc, out = self.run_it(grace=24)
        self.assertEqual(rc, 1)
        self.assertIn("::error::yeetmouse", out)

    def test_conflict_is_never_resubmitted(self):
        self.conflicts[("yeetmouse", F44)] = "published but not as the pinned kernel"
        rc, out = self.run_it()
        self.assertEqual((rc, self.submits), (1, []))
        self.assertIn("not as the pinned kernel", out)

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

    def test_no_ready_chroot_is_an_error(self):
        rc, out = self.run_it(chroots=())
        self.assertEqual(rc, 1)

    def test_bad_arguments(self):
        for arg in ("yeetmouse", "yeetmouse=", "=0^20260803git78dcd0d-1", "yeetmouse=0-1"):
            with self.subTest(arg):
                with self.assertRaises(SystemExit):
                    self.cb._pairs([arg])
        for arg in (RAW, f"{F44} {F44}", "epel-9-x86_64"):
            with self.subTest(arg):
                with self.assertRaises(SystemExit):
                    self.cb._chroot_list(arg)


class KmodPublishedTest(unittest.TestCase):
    """_published for kmod-yeetmouse: only the pinned kernel's package counts,
    and another kernel's package at the same version-release is a conflict."""

    def setUp(self):
        self.cb = helpers.load("copr_build", ENV)
        self.want = self.cb.parse_evr(f"{V}-1")

    def test_pinned_kernel_counts(self):
        Fake(self.cb, {"kmod-yeetmouse": [{"id": 11, "state": "succeeded",
                                           "chroots": [F44]}]},
             {(11, F44): kmod_build()})
        self.assertEqual(self.cb._published(("kmod-yeetmouse", F44), self.want, PINS),
                         (11, None))

    def test_other_kernel_at_same_release_is_a_conflict(self):
        Fake(self.cb, {"kmod-yeetmouse": [{"id": 11, "state": "succeeded",
                                           "chroots": [F44]}]},
             {(11, F44): kmod_build(kernel="7.2.9-200.fc44.x86_64")})
        bid, conflict = self.cb._published(("kmod-yeetmouse", F44), self.want, PINS)
        self.assertEqual(bid, 0)
        self.assertIn("republish yeetmouse-kmod-common", conflict)

    def test_missing_pin_fails(self):
        Fake(self.cb, {}, {})
        with self.assertRaises(SystemExit):
            self.cb._published(("kmod-yeetmouse", F45), self.want, {44: K44})


class ChrootSurveyTest(unittest.TestCase):
    def setUp(self):
        self.cb = helpers.load("copr_build", ENV)
        self.active = {F44, F45, RAW, "epel-9-x86_64"}
        self.project = {F44, F45, RAW}
        self.cfg = {c: {"additional_packages": ["kmodtool", "kernel-devel"],
                        "delete_after_days": None} for c in self.project}
        self.cb._active_mock_chroots = lambda: set(self.active)
        self.cb._project_chroots = lambda: set(self.project)
        self.cb._project_chroot = lambda c: self.cfg[c]

    def test_ready_excludes_rawhide(self):
        ready, problems, _ = self.cb.survey_chroots()
        self.assertEqual((ready, problems), ([F44, F45], []))

    def test_missing_packages_is_a_problem(self):
        self.cfg[F45] = {"additional_packages": ["kmodtool"], "delete_after_days": None}
        ready, problems, _ = self.cb.survey_chroots()
        self.assertEqual(ready, [F44])
        self.assertIn("kernel-devel", problems[0])
        rc, out = quiet(self.cb.check_chroots)
        self.assertEqual(rc, 1)

    def test_scheduled_for_deletion_is_not_ready(self):
        self.cfg[F44] = dict(self.cfg[F44], delete_after_days=180)
        ready, problems, _ = self.cb.survey_chroots()
        self.assertEqual(ready, [F45])
        self.assertIn("scheduled for deletion", problems[0])

    def test_inactive_release_is_skipped_quietly(self):
        self.active.discard(F44)
        ready, problems, notes = self.cb.survey_chroots()
        self.assertEqual((ready, problems), ([F45], []))
        self.assertIn("end of life", notes[0])

    def test_newer_release_offered_but_missing_is_a_problem(self):
        self.active.add("fedora-46-x86_64")
        ready, problems, _ = self.cb.survey_chroots()
        self.assertEqual(ready, [F44, F45])
        self.assertIn("fedora-46-x86_64", problems[0])

    def test_check_chroots_passes_when_all_ready(self):
        rc, out = quiet(self.cb.check_chroots)
        self.assertEqual(rc, 0, out)

    def test_release_of(self):
        self.assertEqual(self.cb.release_of(F45), 45)
        for chroot in ("epel-9-x86_64", RAW, "fedora-44-aarch64"):
            with self.subTest(chroot):
                with self.assertRaises(SystemExit):
                    self.cb.release_of(chroot)


if __name__ == "__main__":
    unittest.main()
