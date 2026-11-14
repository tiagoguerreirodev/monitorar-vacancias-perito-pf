"""Real owner lifecycle; only host/filesystem syscall boundaries are adapted.

Never run the privileged helper directly: redirect /opt and /proc to temporary
unprivileged fixtures and emulate root metadata at the lstat trust boundary.
No ownership, staging, handler, or cleanup implementation is replaced.
"""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
OWNER = ROOT / '.github/scripts/sandbox-owner.py'

HARNESS = r'''
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
from unittest.mock import patch

if os.geteuid() == 0:
    raise RuntimeError('unprivileged fixture required')
spec = importlib.util.spec_from_file_location('sandbox_owner', sys.argv[1])
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
root = Path(sys.argv[2]).resolve()
mode = sys.argv[3]
signum = int(sys.argv[4])
source = root / 'source'
source.mkdir()
(root / 'opt').mkdir()
(root / 'proc').mkdir()
if mode == 'preexisting':
    existing = root / 'opt' / ('perito-uf-sandbox-' + 'a' * 32)
    existing.mkdir()
    (existing / 'sentinel').write_text('not owned by helper')
owner.PROFILES = root / 'apparmor-profiles'
owner.PROFILES.write_text('')
uid, gid = os.getuid(), os.getgid()
real_mkdir, real_lstat = Path.mkdir, Path.lstat
report = {'boundary_reached': False}


def host_path(value):
    # The real helper still derives its own name and all paths from OS boundaries.
    return {'/opt': root / 'opt', '/proc': root / 'proc'}.get(str(value), Path(value))


def host_lstat(path, *args, **kwargs):
    info = real_lstat(path, *args, **kwargs)
    if path == root or root in path.parents or path in root.parents:
        fields = list(info)
        fields[0] &= ~0o022
        fields[4] = 0
        return os.stat_result(fields)
    return info


def mkdir_boundary(path, *args, **kwargs):
    if path.parent != root / 'opt':
        return real_mkdir(path, *args, **kwargs)
    report['boundary_reached'] = True
    if mode == 'collision':
        # A competitor wins after the helper's existence check, before mkdir.
        real_mkdir(path)
        (path / 'sentinel').write_text('not owned by helper')
    result = real_mkdir(path, *args, **kwargs)  # Actual exclusive OS creation.
    report['mask_at_creation'] = sorted(signal.pthread_sigmask(signal.SIG_BLOCK, []))
    os.kill(os.getpid(), signum)  # Exact successful-syscall -> recording window.
    report['pending_after_send'] = signum in signal.sigpending()
    return result


# Preserve both an unrelated blocked signal and a handled one (not the injected signal).
blocked_handled = signal.SIGALRM if signum != signal.SIGALRM else signal.SIGHUP
previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGUSR1, blocked_handled})
report['mask_before'] = sorted(signal.pthread_sigmask(signal.SIG_BLOCK, []))
try:
    with patch.object(owner, 'Path', host_path), patch.object(Path, 'lstat', host_lstat), \
            patch.object(Path, 'mkdir', mkdir_boundary), \
            patch.object(owner.platform, 'system', return_value='Linux'), \
            patch.object(owner.os, 'geteuid', return_value=0), \
            patch.object(owner.secrets, 'token_hex', return_value='a' * 32), \
            patch.dict(os.environ, {'SUDO_UID': str(uid), 'SUDO_GID': str(gid)}), \
            patch.object(sys, 'argv', ['sandbox-owner.py', str(source), str(uid), str(gid)]):
        code = owner.main()
    report['mask_after'] = sorted(signal.pthread_sigmask(signal.SIG_BLOCK, []))
    (root / 'report.json').write_text(json.dumps(report))
finally:
    signal.pthread_sigmask(signal.SIG_SETMASK, previous)
raise SystemExit(code)
'''


@unittest.skipUnless(hasattr(signal, 'pthread_sigmask'), 'POSIX signal masks required')
class OwnerSignalTests(unittest.TestCase):
    def run_owner(self, root, signum, mode='interrupt'):
        result = subprocess.run([sys.executable, '-c', HARNESS, str(OWNER), str(root),
                                 mode, str(int(signum))], input='{"action":"stage"}\n',
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipts = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(receipts), 1, result.stdout)
        self.assertTrue(all(receipts[0].values()), receipts)
        report = json.loads((root / 'report.json').read_text())
        self.assertEqual(report['boundary_reached'], mode != 'preexisting')
        self.assertEqual(report['mask_after'], report['mask_before'])
        return report

    def test_interruption_after_exclusive_creation_removes_actual_owned_directory(self):
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
            with self.subTest(signal=signum), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report = self.run_owner(root, signum)
                self.assertEqual(list((root / 'opt').iterdir()), [],
                                 'successful cleanup receipt must not hide a leaked directory')
                self.assertTrue(report['pending_after_send'])
                self.assertIn(signum, report['mask_at_creation'])

    def test_collisions_remain_untouched_and_restore_prior_mask(self):
        for mode in ('collision', 'preexisting'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.run_owner(root, signal.SIGTERM, mode)
                entries = list((root / 'opt').iterdir())
                self.assertEqual(len(entries), 1)
                self.assertEqual([path.name for path in entries[0].iterdir()], ['sentinel'])
                self.assertEqual((entries[0] / 'sentinel').read_text(), 'not owned by helper')


if __name__ == '__main__':
    unittest.main()
