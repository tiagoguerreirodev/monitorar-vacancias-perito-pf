"""The CLI wraps the same full refresh/build operation used by acceptance tests."""
import subprocess
import sys
import unittest


class CommandTests(unittest.TestCase):
    def test_module_command_exposes_dedicated_data_and_site_directories(self):
        result = subprocess.run([sys.executable, "-m", "perito_dashboard", "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--data-dir", result.stdout)
        self.assertIn("--site-dir", result.stdout)


if __name__ == "__main__":
    unittest.main()
