"""Unprivileged real owner protocol/syscall fixtures, not Linux/root evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.test_sandbox_experiment import api

ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / '.github/scripts/sandbox-owner.py'
HARNESS = r'''
import importlib.util
import os
from pathlib import Path
import sys
from unittest.mock import patch
if os.geteuid() == 0:
    raise RuntimeError('unprivileged fixture required')
spec = importlib.util.spec_from_file_location('owner', sys.argv[1])
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
root, mode = Path(sys.argv[2]).resolve(), sys.argv[3]
source = root / 'source'
source.mkdir()
(source / 'file').write_text('fixture bytes')
for name in ('opt', 'proc', 'usr', 'usr/lib'):
    (root / name).mkdir(exist_ok=True)
owner.PROFILES = root / 'policies'
owner.PROFILES.write_text('')
real_lstat, real_chmod, real_unlink = Path.lstat, Path.chmod, os.unlink
uid, gid = os.getuid(), os.getgid()
def host_path(value):
    return {'/': root, '/opt': root / 'opt', '/proc': root / 'proc',
            '/usr': root / 'usr', '/usr/lib': root / 'usr/lib'}.get(str(value), Path(value))
def host_lstat(path, *args, **kwargs):
    info = real_lstat(path, *args, **kwargs)
    fields = list(info)
    fields[4] = 0
    fields[0] &= ~0o022
    if mode == 'known' and path == root / 'opt':
        fields[0] |= 0o020
    return os.stat_result(fields)
def chmod_boundary(path, *args, **kwargs):
    if mode in ('unknown', 'unclean', 'runtime_error') and 'runtime' in path.parts:
        error = RuntimeError if mode == 'runtime_error' else OSError
        raise error('SECRET /private/path token=cookie ws://devtools')
    return real_chmod(path, *args, **kwargs)
def unlink_boundary(path, *args, **kwargs):
    if mode == 'unclean' and 'dir_fd' in kwargs:
        raise PermissionError('SECRET cleanup')
    return real_unlink(path, *args, **kwargs)
with patch.object(owner, 'Path', host_path), patch.object(Path, 'lstat', host_lstat), \
        patch.object(Path, 'chmod', chmod_boundary), patch.object(os, 'unlink', unlink_boundary), \
        patch.object(owner.platform, 'system', return_value='Linux'), \
        patch.object(owner.os, 'geteuid', return_value=0), \
        patch.dict(os.environ, {'SUDO_UID': str(uid), 'SUDO_GID': str(gid)}), \
        patch.object(sys, 'argv', ['sandbox-owner.py', str(source), str(uid), str(gid)]):
    code = owner.main()
raise SystemExit(code)
'''


class StageDiagnosisTests(unittest.TestCase):
    def command(self, root, mode):
        return [sys.executable, '-c', HARNESS, str(OWNER), str(root), mode]

    def test_known_owner_refusal_retains_classification_and_real_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = api().experiment(self.command(root, 'known'), ['never-observe'])
            self.assertEqual(result['status'], 'experiment_failed')
            self.assertEqual(result['owner_failure'], {'action': 'stage', 'reason': 'ancestor_unprotected'})
            self.assertEqual(result['cleanup'], {'profile_removed': True, 'runtime_removed': True,
                                                 'processes_stopped': True})
            self.assertEqual(list((root / 'opt').iterdir()), [])
            self.assertTrue(result['candidate_ancestors']['opt']['group_or_world_writable'])
            self.assertNotIn(str(root), json.dumps(result))

    def test_unknown_secret_error_is_generic_and_owned_directory_really_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = api().experiment(self.command(root, 'unknown'), ['never-observe'])
            self.assertEqual(result['owner_failure'], {'action': 'stage', 'reason': 'unexpected_error'})
            self.assertTrue(all(result['cleanup'].values()))
            self.assertEqual(list((root / 'opt').iterdir()), [])
            for secret in ('SECRET', '/private', 'cookie', 'devtools', str(root)):
                self.assertNotIn(secret, json.dumps(result))

    def test_malformed_failure_receipts_cannot_claim_cleanup_or_leak(self):
        facts = {key: {'directory': True, 'non_symlink': True, 'root_owned': True,
                       'group_or_world_writable': False} for key in ('root', 'opt', 'usr', 'usr_lib')}
        valid = {'ok': True, 'profile_removed': True, 'runtime_removed': True, 'processes_stopped': True,
                 'failure': {'action': 'stage', 'reason': 'ancestor_unprotected'}, 'candidate_ancestors': facts}
        cases = []
        for change in ({'failure': {'action': 'stage', 'reason': 'SECRET /private'}},
                       {'failure': {'action': 'load', 'reason': 'collision'}},
                       {'failure': {'action': 'stage', 'reason': []}},
                       {'raw': 'SECRET /private'}, {'runtime_removed': 1},
                       {'candidate_ancestors': {'raw': 'SECRET'}}):
            cases.append(json.dumps({**valid, **change}))
        cases += ['{"ok":', 'SECRET ' * 1000, '[' * 1500 + ']' * 1500,
                  json.dumps(valid)[:-1] + ', "failure": {"action":"stage","reason":"collision"}}']
        for payload in cases:
            with self.subTest(payload=payload[:40]), tempfile.TemporaryDirectory() as directory:
                helper = Path(directory) / 'helper.py'
                helper.write_text('import sys\nsys.stdin.readline()\nprint(' + repr(payload) + ', flush=True)\n')
                result = api().experiment([sys.executable, str(helper)], ['never-observe'])
                self.assertEqual(result['status'], 'cleanup_failed')
                self.assertFalse(any(result['cleanup'].values()))
                self.assertNotIn('owner_failure', result)
                self.assertNotIn('candidate_ancestors', result)
                self.assertNotIn('SECRET', json.dumps(result))
                self.assertNotIn('/private', json.dumps(result))

    def test_invalid_owner_protocol_is_bounded_generic_and_cleanup_is_real(self):
        for payload in ('[]\n', '{"action": []}\n', '{"action":"SECRET"}\n',
                        'SECRET' * 1000 + '\n', '{"action":"stage","action":"load"}\n'):
            with self.subTest(payload=payload[:30]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                process = subprocess.run(self.command(root, 'normal'), input=payload,
                                         text=True, capture_output=True, timeout=10)
                self.assertEqual(process.stderr, '')
                receipt = json.loads(process.stdout)
                self.assertEqual(receipt['failure'], {'action': 'protocol', 'reason': 'invalid_request'})
                self.assertTrue(receipt['runtime_removed'])
                self.assertEqual(list((root / 'opt').iterdir()), [])
                self.assertNotIn('SECRET', process.stdout)

    def test_failure_retains_actual_incomplete_cleanup_after_owner_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = api().experiment(self.command(root, 'unclean'), ['never-observe'])
            self.assertEqual(result['status'], 'cleanup_failed')
            self.assertEqual(result['owner_failure'], {'action': 'stage', 'reason': 'unexpected_error'})
            self.assertEqual(result['cleanup'], {'profile_removed': True, 'runtime_removed': False,
                                                 'processes_stopped': True})
            self.assertEqual(len(list((root / 'opt').iterdir())), 1)
            self.assertNotIn('SECRET', json.dumps(result))

    def test_non_os_secret_exception_is_generic_at_real_syscall_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = api().experiment(self.command(root, 'runtime_error'), ['never-observe'])
            self.assertEqual(result['owner_failure'], {'action': 'stage', 'reason': 'unexpected_error'})
            self.assertTrue(all(result['cleanup'].values()))
            self.assertEqual(list((root / 'opt').iterdir()), [])
            self.assertNotIn('SECRET', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
