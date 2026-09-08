"""Exercise installation and replacement without network or Slurm access."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sinner-top-install-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dest = self.root / "user's bin"
        self.env = dict(os.environ, SINNER_TOP_INSTALL_DIR=str(self.dest), SINNER_TOP_BASE_URL=ROOT.as_uri())

    def install(self, source=None):
        env = dict(self.env)
        if source is not None:
            env["SINNER_TOP_BASE_URL"] = source.as_uri()
        return subprocess.run(["sh", str(ROOT / "install.sh")], env=env, text=True, capture_output=True, timeout=15)

    def assert_no_temporary_files(self):
        self.assertEqual(list(self.dest.glob(".sinner-top.*")), [])

    def test_install_and_path_hint(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.dest / "sinner-top"
        self.assertEqual(installed.read_bytes(), (ROOT / "sinner-top").read_bytes())
        self.assertTrue(os.access(installed, os.X_OK))
        help_result = subprocess.run([str(installed), "--help"], text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        export = next(line.strip() for line in result.stdout.splitlines() if line.strip().startswith("export PATH="))
        path_result = subprocess.run(["sh", "-c", export + '\nprintf "%s" "$PATH"'], env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(path_result.stdout.split(os.pathsep)[0], str(self.dest))
        self.assert_no_temporary_files()

    def test_update_replaces_existing_file(self):
        self.dest.mkdir()
        (self.dest / "sinner-top").write_text("old version\n")
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.dest / "sinner-top").read_bytes(), (ROOT / "sinner-top").read_bytes())
        self.assert_no_temporary_files()

    def test_download_failure_preserves_existing_file(self):
        self.dest.mkdir()
        target = self.dest / "sinner-top"
        target.write_text("old version\n")
        result = self.install(self.root / "missing-source")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "old version\n")
        self.assert_no_temporary_files()

    def test_invalid_python_preserves_existing_file(self):
        self.dest.mkdir()
        target = self.dest / "sinner-top"
        target.write_text("old version\n")
        source = self.root / "invalid-source"
        source.mkdir()
        (source / "sinner-top").write_text("This is not valid Python.\n")
        result = self.install(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "old version\n")
        self.assert_no_temporary_files()

    def run_update(self, source, entry=None):
        target = self.dest / "sinner-top"
        env = dict(self.env, SINNER_TOP_BASE_URL=source.as_uri())
        return subprocess.run([sys.executable, str(entry or target), "update"], env=env,
                              text=True, capture_output=True, timeout=15)

    def test_self_update_replaces_invoked_script_without_slurm(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.dest / "sinner-top"
        original = target.read_bytes()
        source = self.root / "new-release"
        source.mkdir()
        newest = original + b"\n# New release fixture.\n"
        (source / "sinner-top").write_bytes(newest)
        result = self.run_update(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Updated: {target}", result.stdout)
        self.assertEqual(target.read_bytes(), newest)
        self.assertTrue(os.access(target, os.X_OK))
        result = self.run_update(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Already up to date", result.stdout)
        self.assert_no_temporary_files()

    def test_self_update_failure_preserves_installed_bytes(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.dest / "sinner-top"
        original = target.read_bytes()
        source = self.root / "broken-release"
        source.mkdir()
        for payload in (b"", b"<html>Error</html>", b"#!/usr/bin/env python3\ndef main(:\n", b"x" * (2 * 1024 * 1024 + 1)):
            (source / "sinner-top").write_bytes(payload)
            result = self.run_update(source)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("kept unchanged", result.stderr)
            self.assertEqual(target.read_bytes(), original)
            self.assert_no_temporary_files()
        result = self.run_update(self.root / "missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), original)
        self.assert_no_temporary_files()

    def test_self_update_preserves_symlink_and_permissions(self):
        self.assertEqual(self.install().returncode, 0)
        target = self.dest / "sinner-top"
        target.chmod(0o750)
        link = self.root / "sinner-link"
        link.symlink_to(target)
        source = self.root / "release"
        source.mkdir()
        newest = target.read_bytes() + b"\n# Symlink update fixture.\n"
        (source / "sinner-top").write_bytes(newest)
        result = self.run_update(source, link)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), newest)
        self.assertEqual(target.stat().st_mode & 0o777, 0o750)
        self.assert_no_temporary_files()


if __name__ == "__main__":
    unittest.main(verbosity=2)
