"""Real owner main with virtual system paths at filesystem/syscall boundaries only.

No root, browser, policy parser, or installed runtime is exercised. Tiny source
and manifest stand-ins let the actual inventory/copy/pin/policy guards complete.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

OWNER = Path(__file__).resolve().parents[1] / '.github/scripts/sandbox-owner.py'
HARNESS = r'''
import hashlib, importlib.util, json, os, shutil, stat, sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
if os.geteuid() == 0:
    raise RuntimeError('unprivileged fixture required')
spec = importlib.util.spec_from_file_location('owner', sys.argv[1])
owner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
root, mode = Path(sys.argv[2]).resolve(), sys.argv[3]
uid, gid = os.getuid(), os.getgid()
for name in ('opt', 'usr', 'usr/lib', 'usr/lib/jvm', 'proc', 'source',
             'source/node', 'source/node/bin', 'source/chrome-linux64',
             'repo', 'repo/perito_dashboard', 'repo/perito_dashboard/collector'):
    (root / name).mkdir()
(root / 'opt').chmod(0o777)
(root / 'usr/lib/jvm').chmod(0o777)
source = root / 'source'
pins = {}
for key, relative in [('node', 'node/bin/node'), ('chrome', 'chrome-linux64/chrome')]:
    data = ('tiny ' + key + ' fixture').encode()
    (source / relative).write_bytes(data)
    (source / relative).chmod(0o755)
    pins[key] = {'executable_sha256': hashlib.sha256(data).hexdigest()}
(root / 'repo/perito_dashboard/collector/runtime.json').write_text(json.dumps(pins))
owner.__file__ = str(root / 'repo/.github/scripts/sandbox-owner.py')
owner.PROFILES = root / 'policies'
owner.PROFILES.write_text('')
name = 'perito-uf-sandbox-' + 'a' * 32
competitor = root / 'usr/lib' / (name if mode == 'collision' else 'perito-uf-sandbox-' + 'b' * 32)
competitor.mkdir()
(competitor / 'sentinel').write_bytes(b'competitor must survive')
(competitor / 'sentinel').chmod(0o640)
real = {key: getattr(Path, key) for key in ('lstat', 'stat', 'open', 'mkdir', 'chmod', 'rglob', 'resolve', 'iterdir')}
copytree, rmtree = shutil.copytree, shutil.rmtree
chown_calls = []
def mapped(path):
    text = str(path)
    if text in ('/', '/opt', '/usr', '/usr/lib', '/proc'):
        return root / text.lstrip('/')
    if text.startswith('/usr/lib/perito-uf-sandbox-') or text.startswith('/opt/perito-uf-sandbox-'):
        return root / text.lstrip('/')
    return path
def metadata(path, *args, **kwargs):
    info = real['lstat'](mapped(path), *args, **kwargs)
    fields = list(info)
    fields[4] = 0
    # Physical fixture ancestors are not system paths; emulate their trust only.
    if path == root or path in root.parents:
        fields[0] &= ~0o022
    if mode == 'unsafe_' + {'/': 'root', '/usr': 'usr', '/usr/lib': 'usr_lib'}.get(str(path), '-'):
        fields[0] |= 0o002
    return os.stat_result(fields)
def boundary(key):
    def call(path, *args, **kwargs):
        return real[key](mapped(path), *args, **kwargs)
    return call
def walk(path, *args, **kwargs):
    for item in real['rglob'](mapped(path), *args, **kwargs):
        yield path / item.relative_to(mapped(path))
def resolve(path, *args, **kwargs):
    if mapped(path) != path:
        real['resolve'](mapped(path), *args, **kwargs)
        return path
    return real['resolve'](path, *args, **kwargs)
def copy(src, dst, *args, **kwargs):
    return copytree(mapped(Path(src)), mapped(Path(dst)), *args, **kwargs)
def remove(path, *args, **kwargs):
    physical = mapped(Path(path))
    # Emulate root's DAC bypass only inside the exclusively created fixture.
    assert physical == root / 'usr/lib' / name and mode != 'collision'
    for entry in [physical, *real['rglob'](physical, '*')]:
        if entry.is_dir():
            real['chmod'](entry, 0o700)
    return rmtree(physical, *args, **kwargs)
def chown(path, target_uid, target_gid, **kwargs):
    info = real['stat'](mapped(path))
    # Observe the actual owner syscall argument, not an Owner attribute.
    (root / 'temporary-sibling.json').write_text(json.dumps({
        'path': str(path), 'mode': stat.S_IMODE(info.st_mode),
        'caller_owned': (info.st_uid, info.st_gid) == (uid, gid),
        'requested_owner': (target_uid, target_gid) == (uid, gid),
        'socket_bytes': [len((str(path) + suffix).encode()) for suffix in (
            '/org.chromium.Chromium.XXXXXX/SingletonSocket',
            '/com.google.Chrome.XXXXXX/SingletonSocket')],
    }))
    assert str(path) == '/usr/lib/' + name + '/p'
    assert (target_uid, target_gid) == (uid, gid)
    assert not (mapped(path).parent / 'profiles').exists()
    assert mapped(path).parent != mapped(Path('/usr/lib/' + name + '/runtime'))
    runtime = mapped(Path('/usr/lib/' + name + '/runtime'))
    assert not real['stat'](runtime).st_mode & 0o022
    assert (mapped(path).parent / 'profile').read_text() == (
        'abi <abi/4.0>,\ninclude <tunables/global>\n\n'
        'profile perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa '
        '"/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime/chrome-linux64/chrome" '
        'flags=(unconfined) {\n  userns,\n}\n')
    chown_calls.append(str(path))
parents = [root, root / 'opt', root / 'usr', root / 'usr/lib', root / 'usr/lib/jvm']
before = [(p.read_bytes(), p.stat().st_mode) for p in [competitor / 'sentinel']]
parent_modes = [p.stat().st_mode for p in parents]
with ExitStack() as stack:
    stack.enter_context(patch.object(Path, 'lstat', metadata))
    for key in ('open', 'mkdir', 'chmod', 'iterdir'):
        stack.enter_context(patch.object(Path, key, boundary(key)))
    stack.enter_context(patch.object(Path, 'stat', boundary('stat')))
    stack.enter_context(patch.object(Path, 'rglob', walk))
    stack.enter_context(patch.object(Path, 'resolve', resolve))
    stack.enter_context(patch.object(shutil, 'copytree', copy))
    stack.enter_context(patch.object(shutil, 'rmtree', remove))
    stack.enter_context(patch.object(os, 'chown', chown))
    stack.enter_context(patch.object(owner.platform, 'system', return_value='Linux'))
    stack.enter_context(patch.object(owner.os, 'geteuid', return_value=0))
    stack.enter_context(patch.object(owner.secrets, 'token_hex', return_value='a' * 32))
    stack.enter_context(patch.dict(os.environ, {'SUDO_UID': str(uid), 'SUDO_GID': str(gid)}))
    stack.enter_context(patch.object(sys, 'argv', ['sandbox-owner.py', str(source), str(uid), str(gid)]))
    code = owner.main()
assert before == [(p.read_bytes(), p.stat().st_mode) for p in [competitor / 'sentinel']]
assert parent_modes == [p.stat().st_mode for p in parents]
assert sorted(p.name for p in (root / 'usr/lib').iterdir()) == ['jvm', competitor.name]
assert not list((root / 'opt').iterdir())
if mode != 'safe':
    assert not chown_calls
raise SystemExit(code)
'''


class ProtectedParentTests(unittest.TestCase):
    def run_owner(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            process = subprocess.run([sys.executable, '-c', HARNESS, str(OWNER), directory, mode],
                                     input='{"action":"stage"}\n{"action":"cleanup"}\n',
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stderr, '')
            if mode == 'safe':
                sibling = json.loads((Path(directory) / 'temporary-sibling.json').read_text())
                # Pinned Linux sun_path[108] reserves one byte for NUL. These
                # literal budgets are independent of the changed implementation.
                self.assertEqual(sibling['socket_bytes'], [106, 102])
                self.assertTrue(all(size <= 107 for size in sibling['socket_bytes']))
                self.assertEqual(sibling['path'],
                                 '/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/p')
                self.assertEqual(sibling['mode'], 0o700)
                self.assertTrue(sibling['caller_owned'])
                self.assertTrue(sibling['requested_owner'])
            return [json.loads(line) for line in process.stdout.splitlines()]

    def test_actual_permission_pattern_stages_under_protected_usr_lib_and_cleans(self):
        receipts = self.run_owner('safe')
        self.assertEqual(len(receipts), 2, receipts)
        self.assertEqual(receipts[0]['runtime'],
                         '/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime')
        self.assertEqual(set(receipts[0]), {'ok', 'runtime', 'tree_sha256'})
        self.assertRegex(receipts[0]['tree_sha256'], r'^[0-9a-f]{64}$')
        self.assertEqual(receipts[1], {'ok': True, 'profile_removed': True,
                                       'runtime_removed': True, 'processes_stopped': True})

    def test_every_unsafe_ancestor_refuses_before_creation_preserving_competitor(self):
        for mode in ('unsafe_root', 'unsafe_usr', 'unsafe_usr_lib'):
            with self.subTest(mode=mode):
                receipts = self.run_owner(mode)
                self.assertEqual(len(receipts), 1)
                self.assertEqual(receipts[0]['failure'],
                                 {'action': 'stage', 'reason': 'ancestor_unprotected'})
                self.assertTrue(receipts[0]['runtime_removed'])

    def test_existing_competitor_capsule_is_never_claimed_or_deleted(self):
        receipts = self.run_owner('collision')
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]['failure'], {'action': 'stage', 'reason': 'collision'})
        self.assertTrue(receipts[0]['runtime_removed'])


if __name__ == '__main__':
    unittest.main()
