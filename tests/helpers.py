"""Helpers shared by the tests: load the scripts under .github/scripts and
build throwaway copies of the repository."""

import importlib.util
import os
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, ".github", "scripts")
SPEC_FILES = ["specs/kmod-yeetmouse.spec", "specs/yeetmouse.spec",
              "specs/yeetmouse-gui.spec"]
LOCAL_SOURCES = ["config.h", "yeetmouse.service", "yeetmouse-preset.conf",
                 "yeetmouse-sysusers.conf", "yeetmouse.conf", ".copr/Makefile",
                 ".external_versions"]


def load(name, env=None):
    """Import .github/scripts/<name>.py as a fresh module."""
    old = {}
    for k, v in (env or {}).items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        spec = importlib.util.spec_from_file_location(
            f"{name}_under_test", os.path.join(SCRIPTS, f"{name}.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout


def copy_repo():
    """A temp directory holding the specs and local sources, as a git repo
    with one commit. Caller removes it."""
    d = tempfile.mkdtemp(prefix="yeetmouse-test-")
    for rel in SPEC_FILES + LOCAL_SOURCES + [".github/scripts/spec_version.py",
                                             ".github/scripts/pin_upstream.sh"]:
        src = os.path.join(ROOT, rel)
        dst = os.path.join(d, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.name", "test")
    git(d, "config", "user.email", "test@example.invalid")
    git(d, "add", "-A")
    git(d, "commit", "-q", "-m", "base")
    return d


def read(d, rel):
    with open(os.path.join(d, rel), encoding="utf-8") as f:
        return f.read()


def write(d, rel, text):
    with open(os.path.join(d, rel), "w", encoding="utf-8") as f:
        f.write(text)
