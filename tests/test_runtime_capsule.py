"""Public lifecycle contracts, external OS/process fixtures; never root evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from perito_dashboard.runtime import UFRuntimeError


class CapsuleTests(unittest.TestCase):
    def test_local_managed_runtime_never_attempts_elevation_or_installation(self):
        from perito_dashboard.runtime import runtime_capsule
        with patch.dict(os.environ, {'PERITO_RUNTIME_ROOT': '/unused', 'GITHUB_ACTIONS': ''}), \
                patch('subprocess.Popen', side_effect=AssertionError('no process permitted')):
            with self.assertRaises(UFRuntimeError):
                with runtime_capsule():
                    self.fail('untrusted context entered')

    def test_client_requires_whole_typed_final_and_successful_owner_exit(self):
        from perito_dashboard._capsule import OwnerClient
        final = '{"ok":true,"profile_removed":true,"runtime_removed":true,"processes_stopped":true}'
        for payload, code, success in ((final, 0, True), (final, 7, False),
                                       (final + '\nSECRET', 0, False),
                                       (final.replace('true}', '1}'), 0, False)):
            with self.subTest(payload=payload, code=code):
                command = [sys.executable, '-c',
                           'import sys; sys.stdin.readline(); print(sys.argv[1],flush=True); sys.exit(int(sys.argv[2]))',
                           payload, str(code)]
                client = OwnerClient(command)
                if success:
                    self.assertEqual(client.finish(), {'profile_removed': True, 'runtime_removed': True,
                                                       'processes_stopped': True, 'owner_exit': 0})
                else:
                    with self.assertRaises(UFRuntimeError):
                        client.finish()
                self.assertIsNotNone(client.process.returncode)

    def test_production_path_budget_counts_full_utf8_tmp_and_profile(self):
        from perito_dashboard._capsule import preflight_paths
        base = '/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/p'
        self.assertEqual(preflight_paths(base, base + '/abcdefgh/run/p-ABCDEF'),
                         {'singleton_socket_bytes': [106, 102], 'profile_socket_bytes': 99})
        for temporary, profile in ((base + 'xx', base + '/p-ABCDEF'),
                                   (base, base + '/abcdefgh/run/clean-profile-ABCDEF'),
                                   (base, base + '/é' * 24)):
            with self.subTest(temporary=temporary, profile=profile):
                with self.assertRaises(UFRuntimeError):
                    preflight_paths(temporary, profile)


if __name__ == '__main__':
    unittest.main()
