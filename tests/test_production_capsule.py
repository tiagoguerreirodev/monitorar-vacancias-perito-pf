"""Public production seam, with only filesystem/process/platform adapters.

The external owner and Node stand-ins are not Linux/source qualification.
"""
from contextlib import contextmanager, ExitStack
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from perito_dashboard import runtime, refresh_and_build
from tests.sources import ControlledArchive, monthly_resource
from tests.test_uf import ExportSource, UnavailableNational, NOW
from perito_dashboard._collector import OfficialUF
from tests.uf_runtime import install_offline_runtime

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = '/usr/lib/perito-uf-sandbox-' + 'a' * 32
TRUSTED = {
    'GITHUB_REPOSITORY': 'tiagoguerreirodev/monitorar-vacancias-perito-pf',
    'GITHUB_REF': 'refs/heads/main', 'GITHUB_ACTIONS': 'true',
    'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux', 'ImageOS': 'ubuntu24',
    'GITHUB_EVENT_NAME': 'workflow_dispatch',
    'GITHUB_WORKFLOW_REF': 'tiagoguerreirodev/monitorar-vacancias-perito-pf/.github/workflows/qualify-uf.yml@refs/heads/main',
}


@contextmanager
def external_capsule(root, documents, failure=''):
    """Map protected OS paths to private test files; never run sudo or a browser."""
    env = install_offline_runtime(root, documents)
    source, mirror = root / 'source', root / 'protected'
    node, chrome = source / 'node/bin/node', source / 'chrome-linux64/chrome'
    node.parent.mkdir(parents=True)
    chrome.parent.mkdir(parents=True)
    node.write_text('#!' + sys.executable + '\nimport runpy,sys\n'
                    'if sys.argv[1:]==["--version"]: print("v26.13.1");sys.exit()\n'
                    'runpy.run_path(' + repr(str(ROOT / 'tests/uf_runtime.py')) + ',run_name="__main__")\n')
    chrome.write_text('#!' + sys.executable + '\nprint("Google Chrome for Testing 157.0.8103.78")\n')
    for path in (node, chrome):
        path.chmod(0o700)
    pins = json.loads(runtime.MANIFEST.read_text())
    pins['python']['version'] = platform.python_version()
    pins['python']['executable_sha256'] = hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest()
    if failure == 'python_pin':
        pins['python']['executable_sha256'] = '0' * 64
    for name, path in [('node', node), ('chrome', chrome)]:
        pins[name]['executable_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    log = root / 'owner-events'
    owner = root / 'external-owner.py'
    owner.write_text('''import json,sys,shutil,os
from pathlib import Path
source,mirror,log,failure=map(str,sys.argv[1:])
for line in sys.stdin:
 action=json.loads(line)['action']
 with open(log,'a') as out: out.write(action+'\\n')
 if action=='stage':
  shutil.copytree(source,Path(mirror)/'runtime');(Path(mirror)/'p').mkdir(mode=0o700)
  response={'ok':True,'runtime':''' + repr(PROTECTED + '/runtime') + ''','tree_sha256':'b'*64}
  if failure=='malformed': response['runtime']=False
 elif action=='verify': response={'ok':True,'tree_sha256':'b'*64}
 elif action=='cleanup':
  shutil.rmtree(mirror)
  response={'ok':True,'profile_removed':failure!='cleanup','runtime_removed':True,'processes_stopped':True}
 else: response={'ok':True}
 print(json.dumps(response),flush=True)
 if action=='cleanup': sys.exit(3 if failure=='exit' else 0)
''')
    original_open, original_stat = Path.open, Path.stat
    original_symlink, original_read = Path.is_symlink, Path.read_text
    original_popen, original_run = subprocess.Popen, subprocess.run
    original_temp = tempfile.TemporaryDirectory
    commands = []

    def mapped(path):
        text = str(path)
        return Path(str(mirror) + text[len(PROTECTED):]) if text.startswith(PROTECTED + '/') else Path(path)

    def popen(command, *args, **kwargs):
        commands.append((list(command), kwargs.get('env')))
        if command[0] == '/usr/bin/sudo':
            if failure == 'privilege':
                raise PermissionError('controlled external privilege refusal')
            command = [sys.executable, str(owner), str(source), str(mirror), str(log), failure]
        else:
            command = [str(mapped(value)) if isinstance(value, (str, Path)) else value for value in command]
        return original_popen(command, *args, **kwargs)

    def run(command, *args, **kwargs):
        return original_run([str(mapped(value)) for value in command], *args, **kwargs)

    class Temporary:
        def __init__(self, *args, **kwargs):
            self.protected = kwargs.get('dir') is not None and str(kwargs['dir']).startswith(PROTECTED)
            if self.protected:
                kwargs['dir'] = mapped(kwargs['dir'])
            self.actual = original_temp(*args, **kwargs)
        def __enter__(self):
            directory = self.actual.__enter__()
            return PROTECTED + directory[len(str(mirror)):] if self.protected else directory
        def __exit__(self, *args):
            return self.actual.__exit__(*args)

    env.update(TRUSTED, PERITO_RUNTIME_ROOT=str(source))
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, env))
        stack.enter_context(patch('platform.system', return_value='Linux'))
        stack.enter_context(patch('platform.machine', return_value='x86_64'))
        stack.enter_context(patch.object(Path, 'open', lambda path, *a, **kw: original_open(mapped(path), *a, **kw)))
        stack.enter_context(patch.object(Path, 'stat', lambda path, *a, **kw: original_stat(mapped(path), *a, **kw)))
        stack.enter_context(patch.object(Path, 'is_symlink', lambda path: original_symlink(mapped(path))))
        stack.enter_context(patch.object(Path, 'read_text', lambda path, *a, **kw:
                                        json.dumps(pins) if path == runtime.MANIFEST else original_read(mapped(path), *a, **kw)))
        stack.enter_context(patch('subprocess.Popen', side_effect=popen))
        stack.enter_context(patch('subprocess.run', side_effect=run))
        stack.enter_context(patch('tempfile.TemporaryDirectory', Temporary))
        yield {'mirror': mirror, 'events': log, 'commands': commands, 'sequence': Path(env['PERITO_TEST_EXPORT_SEQUENCE'])}


class ProductionCapsuleTests(unittest.TestCase):
    def documents(self):
        fixtures = ROOT / 'tests/fixtures/uf'
        return [{'workbook': str(fixtures / ('run-' + number + '.xlsx')),
                 'evidence': str(fixtures / ('run-' + number + '.json'))} for number in ('6', '7')]

    def test_actual_protected_binaries_two_fresh_collects_then_cleanup_then_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            with external_capsule(Path(directory), self.documents()) as os_boundary:
                collector = OfficialUF()
                collector.latest_export()
                self.assertEqual(os_boundary['events'].read_text().splitlines(), ['stage', 'load', 'verify', 'cleanup'])
                self.assertFalse(os_boundary['mirror'].exists())
                self.assertEqual(os_boundary['sequence'].with_suffix('.count').read_text(), '2')
                self.assertEqual(len(collector.proof), 2)
                receipt = collector.runtime_receipt
                self.assertEqual(receipt['before'], receipt['after'])
                self.assertEqual(receipt['protected_tree'], {'before': 'b'*64, 'after': 'b'*64})
                self.assertEqual(receipt['capsule_cleanup'], {'profile_removed': True, 'runtime_removed': True,
                                                           'processes_stopped': True, 'owner_exit': 0})
                launches = [(argv, env) for argv, env in os_boundary['commands'] if len(argv) == 4 and argv[0].endswith('/node/bin/node')]
                self.assertEqual(len(launches), 2)
                for argv, env in launches:
                    self.assertEqual(argv[0], PROTECTED + '/runtime/node/bin/node')
                    self.assertEqual(env['TMPDIR'], PROTECTED + '/p')
                    self.assertTrue(argv[2].startswith(PROTECTED + '/p/'))

    def test_cleanup_or_owner_exit_failure_never_publishes_proof_or_receipt(self):
        for failure in ('cleanup', 'exit'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                with external_capsule(Path(directory), self.documents(), failure) as os_boundary:
                    collector = OfficialUF()
                    with self.assertRaises(runtime.UFRuntimeError):
                        collector.latest_export()
                    self.assertEqual(collector.proof, ())
                    self.assertIsNone(collector.runtime_receipt)
                    self.assertFalse(os_boundary['mirror'].exists())
                    self.assertEqual(os_boundary['sequence'].with_suffix('.count').read_text(), '2')

    def test_actual_protected_binary_mutation_is_rejected_and_cleaned(self):
        with tempfile.TemporaryDirectory() as directory:
            with external_capsule(Path(directory), self.documents()) as os_boundary:
                capsule = None
                with self.assertRaises(runtime.UFRuntimeIntegrityError):
                    with runtime.runtime_capsule() as capsule:
                        with Path(capsule.chrome).open('a') as output:
                            output.write('\n# changed protected bytes\n')
                self.assertIsNone(capsule.receipt)
                self.assertFalse(os_boundary['mirror'].exists())
                self.assertEqual(os_boundary['events'].read_text().splitlines(), ['stage', 'load', 'cleanup'])

    def test_all_four_signals_restore_handlers_and_cleanup_before_escape(self):
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
            with self.subTest(signal=signum), tempfile.TemporaryDirectory() as directory:
                previous = signal.getsignal(signum)
                with external_capsule(Path(directory), self.documents()) as os_boundary:
                    with self.assertRaises(runtime.UFRuntimeError):
                        with runtime.runtime_capsule():
                            os.kill(os.getpid(), signum)
                    self.assertFalse(os_boundary['mirror'].exists())
                    self.assertIs(signal.getsignal(signum), previous)

    def test_privilege_and_malformed_stage_failures_are_uf_local(self):
        for failure in ('privilege', 'malformed', 'cleanup'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data, site = root / 'data', root / 'site'
                refresh_and_build(data, site, source=ControlledArchive(), uf_source=ExportSource(), clock=lambda: NOW)
                before = {name: (data / name).read_bytes() for name in ('uf.json', 'uf-status.json')}
                with external_capsule(root, self.documents(), failure) as os_boundary:
                    result = refresh_and_build(data, site, source=ControlledArchive(dict([monthly_resource('2026-10')])),
                                               clock=lambda: NOW + timedelta(days=1))
                    self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
                    self.assertFalse(os_boundary['mirror'].exists())
                    for name in before:
                        self.assertEqual((data / name).read_bytes(), before[name])
                        self.assertEqual((site / 'data' / name).read_bytes(), before[name])

    def test_protected_uf_advances_when_national_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with external_capsule(root, self.documents()) as os_boundary:
                result = refresh_and_build(root / 'data', root / 'site', source=UnavailableNational(), clock=lambda: NOW)
                self.assertEqual(result, {'national': 'failed', 'uf': 'updated', 'publication': 'partial'})
                self.assertEqual(json.loads((root / 'data/uf.json').read_text())['current']['counts_by_uf']['DF'], 324)
                self.assertFalse(os_boundary['mirror'].exists())

    def test_shared_publication_failure_rolls_back_even_after_capsule_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, site = root / 'data', root / 'site'
            refresh_and_build(data, site, source=ControlledArchive(), uf_source=ExportSource(), clock=lambda: NOW)
            before = {str(p.relative_to(root)): p.read_bytes() for base in (data, site) for p in base.rglob('*') if p.is_file()}
            replace = os.replace
            failed = []
            def unavailable(candidate, target):
                if Path(target).resolve() == site.resolve() and not failed:
                    failed.append(True)
                    raise PermissionError('controlled publication failure')
                return replace(candidate, target)
            with external_capsule(root, self.documents()) as os_boundary:
                with patch('os.replace', side_effect=unavailable), self.assertRaises(PermissionError):
                    refresh_and_build(data, site, source=ControlledArchive(), clock=lambda: NOW)
                self.assertFalse(os_boundary['mirror'].exists())
            self.assertTrue(failed)
            self.assertEqual({str(p.relative_to(root)): p.read_bytes() for base in (data, site) for p in base.rglob('*') if p.is_file()}, before)

    def test_python_executable_pin_is_checked_before_policy_load(self):
        with tempfile.TemporaryDirectory() as directory:
            with external_capsule(Path(directory), self.documents(), 'python_pin') as os_boundary:
                with self.assertRaises(runtime.UFRuntimeIntegrityError):
                    with runtime.runtime_capsule():
                        pass
                self.assertEqual(os_boundary['events'].read_text().splitlines(), ['stage', 'cleanup'])
                self.assertFalse(os_boundary['mirror'].exists())

    def test_untrusted_workflow_repository_and_root_refuse_before_privileged_process(self):
        for changed in ({'GITHUB_REF': 'refs/heads/feature'}, {'GITHUB_REPOSITORY': 'fork/repo'},
                        {'GITHUB_EVENT_NAME': 'pull_request'}, {'ImageOS': 'ubuntu22'},
                        {'RUNNER_ENVIRONMENT': 'self-hosted'}, {'GITHUB_WORKFLOW_REF': 'other'}):
            with self.subTest(changed=changed), patch.dict(os.environ, {**TRUSTED, **changed, 'PERITO_RUNTIME_ROOT': '/unused'}), \
                    patch('platform.system', return_value='Linux'), patch('platform.machine', return_value='x86_64'), \
                    patch('subprocess.Popen') as process:
                with self.assertRaises(runtime.UFRuntimeError):
                    with runtime.runtime_capsule():
                        self.fail('untrusted capsule opened')
                process.assert_not_called()
        with patch.dict(os.environ, {**TRUSTED, 'PERITO_RUNTIME_ROOT': '/unused'}), patch('os.geteuid', return_value=0), \
                patch('subprocess.Popen') as process:
            with self.assertRaises(runtime.UFRuntimeError):
                with runtime.runtime_capsule():
                    self.fail('root capsule opened')
            process.assert_not_called()

    def test_profile_source_layout_matches_preflighted_bound(self):
        source = (ROOT / 'perito_dashboard/collector/browser-probe.mjs').read_text()
        self.assertIn("fs.mkdtempSync(path.join(run,'p-'))", source)
        self.assertNotIn('clean-profile-', source)
