import os
import stat
import subprocess
import tempfile
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

SCRIPT = os.path.join(helpers.ROOT, ".github", "scripts", "sense_kernels.sh")

# A stand-in for docker: records its arguments, and answers like dnf would.
# With updates-testing in play it would return the testing kernel, so the
# answer depends on whether the script restricted the repositories.
FAKE = """#!/bin/bash
echo "$*" >> "$FAKE_LOG"
if [[ " $* " == *" --repo=fedora --repo=updates "* ]]; then
  echo "7.2.9-300.fc${FAKE_N}.x86_64"
else
  echo "7.2.9-301.fc${FAKE_N}.x86_64"
fi
"""


class SenseKernelsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="yeetmouse-sense-")
        self.fake = os.path.join(self.tmp, "docker")
        with open(self.fake, "w") as f:
            f.write(FAKE)
        os.chmod(self.fake, os.stat(self.fake).st_mode | stat.S_IEXEC)
        self.log = os.path.join(self.tmp, "log")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_it(self, chroots, n="45"):
        env = dict(os.environ, CONTAINER_RUNTIME=self.fake, FAKE_LOG=self.log, FAKE_N=n)
        return subprocess.run(["bash", SCRIPT, chroots], env=env,
                              capture_output=True, text=True)

    def test_only_fedora_and_updates_repositories(self):
        r = self.run_it("fedora-45-x86_64")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "fc45=7.2.9-300.fc45.x86_64")
        with open(self.log) as f:
            args = f.read()
        self.assertIn("quay.io/fedora/fedora:45", args)
        self.assertIn("--repo=fedora --repo=updates", args)
        self.assertNotIn("testing", args)

    def test_rejects_rawhide_and_wrong_release(self):
        self.assertNotEqual(self.run_it("fedora-rawhide-x86_64").returncode, 0)
        # The answer must be a kernel for the release asked about.
        self.assertNotEqual(self.run_it("fedora-44-x86_64", n="45").returncode, 0)


if __name__ == "__main__":
    unittest.main()
