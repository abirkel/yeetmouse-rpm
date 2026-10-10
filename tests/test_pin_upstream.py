import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

CUR_SHA = "78dcd0d573bedd5dd7b9e29e9162b28c9eb2fd7b"
NEW_SHA = "c3d12f3313a95f25162a1503be624f3b0617f8c0"


class PinUpstreamTest(unittest.TestCase):
    """Runs .github/scripts/pin_upstream.sh in a clone of a throwaway bare
    'origin', so pushes go nowhere real."""

    def setUp(self):
        self.src = helpers.copy_repo()
        self.tmp = tempfile.mkdtemp(prefix="yeetmouse-origin-")
        self.origin = os.path.join(self.tmp, "origin.git")
        subprocess.run(["git", "clone", "-q", "--bare", self.src, self.origin], check=True)
        self.work = os.path.join(self.tmp, "work")
        subprocess.run(["git", "clone", "-q", self.origin, self.work], check=True)
        helpers.git(self.work, "config", "user.name", "test")
        helpers.git(self.work, "config", "user.email", "test@example.invalid")

    def tearDown(self):
        shutil.rmtree(self.src)
        shutil.rmtree(self.tmp)

    def run_pin(self, sha, date):
        env = dict(os.environ, NEW_SHA=sha, SNAPDATE=date, PUSH_RETRY_SLEEP="0")
        return subprocess.run(["bash", ".github/scripts/pin_upstream.sh"], cwd=self.work,
                              env=env, capture_output=True, text=True)

    def origin_head(self):
        return helpers.git(self.origin, "rev-parse", "main").strip()

    def test_already_pinned_makes_no_commit(self):
        before = self.origin_head()
        r = self.run_pin(CUR_SHA, "20261009")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("main already pins", r.stdout)
        self.assertEqual(self.origin_head(), before)

    def test_specs_pinned_but_external_versions_stale_makes_no_commit(self):
        # .external_versions disagrees with the specs: bump-pin is a no-op and
        # the script must not try to commit nothing.
        path = os.path.join(self.src, ".external_versions")
        helpers.write(self.src, ".external_versions",
                      helpers.read(self.src, ".external_versions").replace(CUR_SHA, "0" * 40))
        helpers.git(self.src, "commit", "-q", "-am", "stale external_versions")
        helpers.git(self.src, "push", "-q", self.origin, "main")
        before = self.origin_head()
        r = self.run_pin(CUR_SHA, "20261009")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nothing to commit", r.stdout)
        self.assertEqual(self.origin_head(), before)
        self.assertTrue(os.path.exists(path))

    def test_new_commit_is_pushed(self):
        before = self.origin_head()
        r = self.run_pin(NEW_SHA, "20261009")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotEqual(self.origin_head(), before)
        spec = helpers.git(self.origin, "show", "main:specs/yeetmouse.spec")
        self.assertIn("%global snapdate 20261009", spec)
        self.assertIn(NEW_SHA, spec)
        ext = helpers.git(self.origin, "show", "main:.external_versions")
        self.assertIn(f"YEETMOUSE_COMMIT={NEW_SHA}", ext)

    def test_same_day_commit_fails_without_push(self):
        before = self.origin_head()
        r = self.run_pin(NEW_SHA, "20260803")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("non-monotonic snapshot date", r.stdout + r.stderr)
        self.assertEqual(self.origin_head(), before)


if __name__ == "__main__":
    unittest.main()
