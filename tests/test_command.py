"""The CLI wraps the same full refresh/build operation used by acceptance tests."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from perito_dashboard import refresh_and_build
from tests.sources import ARCHIVE_URL, CHECK_TIME, ControlledArchive


class CommandTests(unittest.TestCase):
    def test_module_command_exposes_dedicated_data_and_site_directories(self):
        result = subprocess.run([sys.executable, "-m", "perito_dashboard", "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--data-dir", result.stdout)
        self.assertIn("--site-dir", result.stdout)

    def test_failed_collection_reports_nonzero_exit_and_preserves_accepted_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, site = root / "data", root / "site"
            refresh_and_build(data, site, source=ControlledArchive(), clock=lambda: CHECK_TIME)
            before = {path.relative_to(root): path.read_bytes()
                      for path in root.rglob("*") if path.is_file()}
            # run_module uses the same entrypoint as `python -m`; only HTTP is
            # controlled, before the application imports its network dependency.
            program = """
import runpy
import sys
from unittest.mock import patch
sys.argv = ['perito_dashboard', '--data-dir', sys.argv[1], '--site-dir', sys.argv[2]]
with patch('urllib.request.urlopen', side_effect=TimeoutError('controlled archive outage')):
    runpy.run_module('perito_dashboard', run_name='__main__')
"""
            result = subprocess.run([sys.executable, "-c", program, str(data), str(site)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertIn("Refresh/build failed; no candidate published:", result.stderr)
            self.assertIn(ARCHIVE_URL, result.stderr)
            self.assertIn("after 3 attempt(s): controlled archive outage", result.stderr)
            after = {path.relative_to(root): path.read_bytes()
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
