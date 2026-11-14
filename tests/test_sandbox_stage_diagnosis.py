"""Unprivileged real owner protocol/syscall fixtures, not Linux/root evidence."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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
    if mode == 'known' and path in (root / 'opt', root / 'usr/lib'):
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
            self.assertEqual(list((root / 'usr/lib').iterdir()), [])
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
            self.assertEqual(len(list((root / 'usr/lib').iterdir())), 1)
            self.assertNotIn('SECRET', json.dumps(result))

    def test_non_os_secret_exception_is_generic_at_real_syscall_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = api().experiment(self.command(root, 'runtime_error'), ['never-observe'])
            self.assertEqual(result['owner_failure'], {'action': 'stage', 'reason': 'unexpected_error'})
            self.assertTrue(all(result['cleanup'].values()))
            self.assertEqual(list((root / 'usr/lib').iterdir()), [])
            self.assertNotIn('SECRET', json.dumps(result))


# Independent protocol literals: these stand-ins do not import owner/driver parsing.
FINAL_FACTS = {
    'root': {'directory': True, 'non_symlink': True, 'root_owned': True,
             'group_or_world_writable': False},
    'opt': {'directory': True, 'non_symlink': True, 'root_owned': True,
            'group_or_world_writable': False},
    'usr': {'directory': True, 'non_symlink': True, 'root_owned': True,
            'group_or_world_writable': False},
    'usr_lib': {'directory': None, 'non_symlink': None, 'root_owned': None,
                'group_or_world_writable': None},
}
UNREAD_FINAL = {
    'ok': True, 'profile_removed': True, 'runtime_removed': False, 'processes_stopped': True,
    'failure': {'action': 'protocol', 'reason': 'unexpected_error'},
    'candidate_ancestors': FINAL_FACTS,
}
BOUNDARY_OWNER = r'''
import json, os, subprocess, sys, time
from pathlib import Path
root, payload, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
sys.stdin.readline()
print('{"ok":true,"runtime":"/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime","tree_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}', flush=True)
while not (root / 'observing').exists():
    time.sleep(.005)
os.close(0)
sys.stdout.write(payload)
sys.stdout.flush()
if mode == 'held_stdout':
    subprocess.Popen([sys.executable, '-c', """import sys, time
from pathlib import Path
deadline = time.monotonic() + 8
while time.monotonic() < deadline and not Path(sys.argv[1]).exists():
    time.sleep(.01)
""", str(root / 'release')], stdin=subprocess.DEVNULL)
(root / 'finished').touch()
if mode == 'hold':
    time.sleep(2)
elif mode == 'suffix':
    time.sleep(.05)
    sys.stdout.write('SECRET /private/path')
    sys.stdout.flush()
'''
BOUNDARY_OBSERVER = r'''
import sys, time
from pathlib import Path
root = Path(sys.argv[1])
(root / 'observing').touch()
while not (root / 'finished').exists():
    time.sleep(.005)
print('[{"outcome":"ready","launched":true,"port_file_seen":true,"port_alive":true,"readiness":true,"stderr_classes":["none"],"stderr_truncated":false,"exit_code":0,"signal":null,"cleanup":{"process_group_stopped":true,"owned_directory_removed":true}},{"outcome":"ready","launched":true,"port_file_seen":true,"port_alive":true,"readiness":true,"stderr_classes":["none"],"stderr_truncated":false,"exit_code":0,"signal":null,"cleanup":{"process_group_stopped":true,"owned_directory_removed":true}},{"outcome":"ready","launched":true,"port_file_seen":true,"port_alive":true,"readiness":true,"stderr_classes":["none"],"stderr_truncated":false,"exit_code":0,"signal":null,"cleanup":{"process_group_stopped":true,"owned_directory_removed":true}}]')
'''


CLEANUP_OWNER = r'''
import json, sys
from pathlib import Path
trace = Path(sys.argv[1])
for line in sys.stdin:
    action = json.loads(line)['action']
    with trace.open('a') as stream:
        stream.write(action + '\n')
    if action == 'stage':
        print('{"ok":true,"runtime":"/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime","tree_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}', flush=True)
    elif action == 'cleanup':
        print(sys.argv[2], flush=True)
        break
    else:
        print('{"ok":true}', flush=True)
'''
CLEANUP_OBSERVER = r'''
import json, sys
from pathlib import Path
loaded = Path(sys.argv[1]).read_text().splitlines()[-1] == 'load'
if sys.argv[2] == 'baseline' or loaded:
    record = {'outcome': 'ready', 'launched': True, 'port_file_seen': True,
              'port_alive': True, 'readiness': True, 'stderr_classes': ['none'],
              'stderr_truncated': False, 'exit_code': 0, 'signal': None,
              'cleanup': {'process_group_stopped': True, 'owned_directory_removed': True}}
else:
    record = {'outcome': 'early_exit', 'launched': True, 'port_file_seen': False,
              'port_alive': False, 'readiness': False, 'stderr_classes': ['sandbox_refusal'],
              'stderr_truncated': False, 'exit_code': None, 'signal': 'SIGABRT',
              'cleanup': {'process_group_stopped': True, 'owned_directory_removed': True}}
print(json.dumps([record, record, record]))
'''


class FinalReceiptTests(unittest.TestCase):
    def unread_result(self, payload, mode='exit'):
        with tempfile.TemporaryDirectory() as directory:
            return api().experiment(
                [sys.executable, '-c', BOUNDARY_OWNER, directory, payload, mode],
                [sys.executable, '-c', BOUNDARY_OBSERVER, directory])

    def test_unread_final_after_observation_retains_true_and_false_cleanup(self):
        result = self.unread_result(json.dumps(UNREAD_FINAL) + '\n')
        self.assertEqual(result['status'], 'cleanup_failed')
        self.assertEqual(result['cleanup'], {'profile_removed': True, 'runtime_removed': False,
                                             'processes_stopped': True})
        self.assertEqual(result['owner_failure'], {'action': 'protocol', 'reason': 'unexpected_error'})
        self.assertEqual(result['candidate_ancestors'], FINAL_FACTS)
        self.assertEqual(list(result['phases']), ['A1'])

    def test_unread_malformed_final_is_wholly_rejected_without_claims_or_leaks(self):
        payloads = [
            json.dumps({**UNREAD_FINAL, 'failure': {'action': 'protocol', 'reason': 'SECRET'}}),
            json.dumps({**UNREAD_FINAL, 'failure': {'action': 'load', 'reason': 'collision'}}),
            json.dumps({**UNREAD_FINAL, 'runtime_removed': 1}),
            json.dumps({**UNREAD_FINAL, 'candidate_ancestors': {'raw': 'SECRET /private'}}),
            json.dumps({**UNREAD_FINAL, 'raw': 'SECRET /private'}),
            json.dumps(UNREAD_FINAL)[:-1] + ',"runtime_removed":true}',
            '{"ok":', 'SECRET /private ' * 500, '[' * 1500 + ']' * 1500,
        ]
        for payload in payloads:
            with self.subTest(payload=payload[:40]):
                result = self.unread_result(payload + '\n')
                self.assertEqual(result['status'], 'cleanup_failed')
                self.assertEqual(result['cleanup'], {'profile_removed': False, 'runtime_removed': False,
                                                     'processes_stopped': False})
                self.assertNotIn('owner_failure', result)
                self.assertNotIn('candidate_ancestors', result)
                self.assertNotIn('SECRET', json.dumps(result))
                self.assertNotIn('/private', json.dumps(result))

    def test_recovery_requires_whole_final_not_just_valid_first_line(self):
        result = self.unread_result(json.dumps(UNREAD_FINAL) + '\n', 'suffix')
        self.assertEqual(result['cleanup'], {'profile_removed': False, 'runtime_removed': False,
                                             'processes_stopped': False})
        self.assertNotIn('owner_failure', result)
        self.assertNotIn('SECRET', json.dumps(result))

    def test_closed_input_with_live_owner_and_held_stdout_finishes_boundedly(self):
        start = time.monotonic()
        result = self.unread_result('', 'hold')
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(result['status'], 'cleanup_failed')
        self.assertFalse(any(result['cleanup'].values()))
        self.assertNotIn('owner_failure', result)

    def test_exited_owner_with_inherited_stdout_cannot_block_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            # The owner exits, but its separate pipe holder cannot close stdout
            # until this outer watchdog releases it. No driver internals patched.
            command = [sys.executable, '-c',
                       'import json, sys; from tests.test_sandbox_experiment import api; '
                       'print(json.dumps(api().experiment(json.loads(sys.argv[1]), json.loads(sys.argv[2]))))',
                       json.dumps([sys.executable, '-c', BOUNDARY_OWNER, directory, '', 'held_stdout']),
                       json.dumps([sys.executable, '-c', BOUNDARY_OBSERVER, directory])]
            start = time.monotonic()
            try:
                process = subprocess.run(command, capture_output=True, text=True, timeout=5)
                self.assertLess(time.monotonic() - start, 3)
                self.assertEqual(process.returncode, 0, process.stderr)
                result = json.loads(process.stdout)
                self.assertEqual(result['status'], 'cleanup_failed')
                self.assertFalse(any(result['cleanup'].values()))
                self.assertNotIn('owner_failure', result)
            finally:
                (Path(directory) / 'release').touch()

    def test_unread_all_true_failure_cannot_preserve_baseline_status(self):
        receipt = {**UNREAD_FINAL, 'runtime_removed': True}
        result = self.unread_result(json.dumps(receipt) + '\n')
        self.assertEqual(result['status'], 'experiment_failed')
        self.assertEqual(result['owner_failure'], {'action': 'protocol', 'reason': 'unexpected_error'})
        self.assertEqual(result['cleanup'], {'profile_removed': True, 'runtime_removed': True,
                                             'processes_stopped': True})

    def cleanup_result(self, payload, mode):
        with tempfile.TemporaryDirectory() as directory:
            trace = str(Path(directory) / 'trace')
            return api().experiment(
                [sys.executable, '-c', CLEANUP_OWNER, trace, json.dumps(payload)],
                [sys.executable, '-c', CLEANUP_OBSERVER, trace, mode])

    def test_cleanup_failure_overrides_baseline_and_would_be_reversible_effect(self):
        receipt = {'ok': True, 'profile_removed': True, 'runtime_removed': True,
                   'processes_stopped': True,
                   'failure': {'action': 'cleanup', 'reason': 'unexpected_error'},
                   'candidate_ancestors': FINAL_FACTS}
        for mode, phases in [('baseline', ['A1']), ('aba', ['A1', 'B', 'A2'])]:
            with self.subTest(mode=mode):
                result = self.cleanup_result(receipt, mode)
                self.assertEqual(result['status'], 'experiment_failed')
                self.assertEqual(result['cleanup'], {'profile_removed': True, 'runtime_removed': True,
                                                     'processes_stopped': True})
                self.assertEqual(result['owner_failure'], {'action': 'cleanup', 'reason': 'unexpected_error'})
                self.assertEqual(result['candidate_ancestors'], FINAL_FACTS)
                self.assertEqual(list(result['phases']), phases)

    def test_ordinary_cleanup_preserves_baseline_and_reversible_effect(self):
        receipt = {'ok': True, 'profile_removed': True, 'runtime_removed': True,
                   'processes_stopped': True}
        for mode, status in [('baseline', 'baseline_not_reproduced'), ('aba', 'reversible_effect')]:
            with self.subTest(mode=mode):
                result = self.cleanup_result(receipt, mode)
                self.assertEqual(result['status'], status)
                self.assertEqual(result['cleanup'], {'profile_removed': True, 'runtime_removed': True,
                                                     'processes_stopped': True})
                self.assertNotIn('owner_failure', result)
                self.assertNotIn('candidate_ancestors', result)


if __name__ == '__main__':
    unittest.main()
