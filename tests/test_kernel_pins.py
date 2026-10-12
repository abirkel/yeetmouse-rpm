import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

KMOD = "specs/kmod-yeetmouse.spec"
NEW_SHA = "c3d12f3313a95f25162a1503be624f3b0617f8c0"


def sv(d, *args):
    return subprocess.run([sys.executable, ".github/scripts/spec_version.py", *args],
                          cwd=d, capture_output=True, text=True)


class KernelPinTest(unittest.TestCase):
    def setUp(self):
        self.d = helpers.copy_repo()
        self.pins = dict(p.split("=") for p in sv(self.d, "kernel-pins").stdout.split())

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_repo_spec_has_pins_for_44_and_45(self):
        self.assertEqual(sorted(self.pins), ["fc44", "fc45"])

    def test_set_moves_and_adds_and_keeps_order(self):
        r = sv(self.d, "set-kernels", "fc46=7.3.0-100.fc46.x86_64",
               "fc44=7.2.10-200.fc44.x86_64")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = helpers.read(self.d, KMOD)
        lines = [line for line in text.splitlines()
                 if line.startswith("%global target_kernel_fc")]
        self.assertEqual(lines, [
            "%global target_kernel_fc44 7.2.10-200.fc44.x86_64",
            f"%global target_kernel_fc45 {self.pins['fc45']}",
            "%global target_kernel_fc46 7.3.0-100.fc46.x86_64"])
        # Release is the caller's job.
        self.assertIn("Release:        2%{?dist}", text)

    def test_unchanged(self):
        r = sv(self.d, "set-kernels", f"fc44={self.pins['fc44']}")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "unchanged"))

    def test_only_newer_never_moves_a_pin_back(self):
        r = sv(self.d, "set-kernels", "--only-newer", "fc44=7.2.9-200.fc44.x86_64")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("not newer", r.stdout)
        self.assertIn(f"target_kernel_fc44 {self.pins['fc44']}", helpers.read(self.d, KMOD))

    def test_bad_pins_rejected(self):
        for arg in ("fc44=7.2.9-301.fc45.x86_64", "fc44=7.2.9-201.fc44.aarch64",
                    "44=7.2.9-201.fc44.x86_64", "fc44="):
            with self.subTest(arg):
                self.assertNotEqual(sv(self.d, "set-kernels", arg).returncode, 0)

    def test_malformed_pin_line_rejected(self):
        helpers.write(self.d, KMOD, helpers.read(self.d, KMOD).replace(
            "%global target_kernel_fc45 ", "%global  target_kernel_fc45 "))
        self.assertNotEqual(sv(self.d, "kernel-pins").returncode, 0)

    def test_rpmvercmp(self):
        sv_mod = helpers.load("spec_version")
        for new, old, want in (
                ("7.2.10-200.fc44.x86_64", "7.2.9-201.fc44.x86_64", True),
                ("7.2.9-201.fc44.x86_64", "7.2.9-200.fc44.x86_64", True),
                ("7.2.9-200.fc44.x86_64", "7.2.9-201.fc44.x86_64", False),
                ("7.2.9-201.fc44.x86_64", "7.2.9-201.fc44.x86_64", False),
                ("7.10.0-100.fc44.x86_64", "7.9.20-300.fc44.x86_64", True)):
            with self.subTest((new, old)):
                self.assertEqual(sv_mod.kernel_newer(new, old), want)

    def test_rpmvercmp_matches_rpm(self):
        try:
            import rpm
        except ImportError:
            self.skipTest("rpm Python bindings not installed")
        sv_mod = helpers.load("spec_version")
        pairs = [("7.2.10", "7.2.9"), ("200.fc44", "201.fc44"), ("1a", "1"),
                 ("1.0", "1.0.1"), ("010", "10"), ("2.fc44.1", "2.fc44")]
        for a, b in pairs:
            with self.subTest((a, b)):
                self.assertEqual(sv_mod.rpmvercmp(a, b), rpm.labelCompare(("0", a, "1"),
                                                                          ("0", b, "1")))


class PinScriptsTest(unittest.TestCase):
    """pin_kernels.sh and pin_upstream.sh in a clone of a throwaway bare
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
        self.pins = sv(self.work, "kernel-pins").stdout.split()

    def tearDown(self):
        shutil.rmtree(self.src)
        shutil.rmtree(self.tmp)

    def run_script(self, name, **env):
        env = dict(os.environ, PUSH_RETRY_SLEEP="0", **env)
        return subprocess.run(["bash", f".github/scripts/{name}"], cwd=self.work,
                              env=env, capture_output=True, text=True)

    def origin_head(self):
        return helpers.git(self.origin, "rev-parse", "main").strip()

    def origin_kmod(self):
        return helpers.git(self.origin, "show", f"main:{KMOD}")

    def test_current_pins_make_no_commit(self):
        before = self.origin_head()
        r = self.run_script("pin_kernels.sh", KERNEL_PINS=" ".join(self.pins))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("kernel pins are current", r.stdout)
        self.assertEqual(self.origin_head(), before)

    def test_older_kernel_makes_no_commit(self):
        before = self.origin_head()
        r = self.run_script("pin_kernels.sh", KERNEL_PINS="fc44=7.2.9-200.fc44.x86_64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.origin_head(), before)

    def test_new_kernel_moves_pin_and_raises_release_once(self):
        r = self.run_script("pin_kernels.sh",
                            KERNEL_PINS="fc44=7.2.10-200.fc44.x86_64 fc45=7.2.9-301.fc45.x86_64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        spec = self.origin_kmod()
        self.assertIn("%global target_kernel_fc44 7.2.10-200.fc44.x86_64", spec)
        self.assertIn("Release:        3%{?dist}", spec)
        self.assertEqual(helpers.git(self.origin, "rev-list", "--count", "main").strip(), "2")
        # Running again with the same kernels changes nothing.
        helpers.git(self.work, "fetch", "-q", "origin")
        before = self.origin_head()
        r = self.run_script("pin_kernels.sh",
                            KERNEL_PINS="fc44=7.2.10-200.fc44.x86_64 fc45=7.2.9-301.fc45.x86_64")
        self.assertEqual((r.returncode, self.origin_head()), (0, before), r.stdout)

    def test_new_release_gets_a_pin_and_a_release_bump(self):
        r = self.run_script("pin_kernels.sh",
                            KERNEL_PINS=" ".join(self.pins + ["fc46=7.3.0-100.fc46.x86_64"]))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        spec = self.origin_kmod()
        self.assertIn("%global target_kernel_fc46 7.3.0-100.fc46.x86_64", spec)
        self.assertIn("Release:        3%{?dist}", spec)

    def test_upstream_bump_refreshes_pins_in_the_same_commit(self):
        r = self.run_script("pin_upstream.sh", NEW_SHA=NEW_SHA, SNAPDATE="20261009",
                            KERNEL_PINS="fc44=7.2.10-200.fc44.x86_64")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        spec = self.origin_kmod()
        self.assertIn("%global target_kernel_fc44 7.2.10-200.fc44.x86_64", spec)
        self.assertIn("Release:        1%{?dist}", spec)
        self.assertIn("%global snapdate 20261009", spec)
        self.assertEqual(helpers.git(self.origin, "rev-list", "--count", "main").strip(), "2")


if __name__ == "__main__":
    unittest.main()
