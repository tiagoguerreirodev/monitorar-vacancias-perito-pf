"""[DEBUG-uf-linux] Offline boundary tests; never Linux/AppArmor evidence."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '.github/scripts/sandbox-experiment.py'


def api():
    spec = importlib.util.spec_from_file_location('sandbox_experiment', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExperimentTests(unittest.TestCase):
    def test_workflow_is_temporary_manual_main_readonly_and_single_artifact(self):
        config = json.loads((ROOT / '.github/workflows/sandbox-experiment.yml').read_text())
        self.assertEqual(config['on'], {'workflow_dispatch': {}})
        self.assertEqual(config['permissions'], {'contents': 'read'})
        self.assertEqual(set(config['jobs']), {'experiment'})
        job = config['jobs']['experiment']
        self.assertEqual(job['runs-on'], 'ubuntu-24.04')
        self.assertEqual(job['if'], "${{ github.repository == 'tiagoguerreirodev/monitorar-vacancias-perito-pf' && github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch' }}")
        self.assertEqual(job['timeout-minutes'], 15)
        self.assertEqual(job['steps'][0]['with'], {'ref': '${{ github.sha }}', 'persist-credentials': False})
        self.assertEqual(job['steps'][-1]['with']['path'], 'uf-sandbox-experiment.json')
        self.assertEqual([step['run'] for step in job['steps'] if 'run' in step], [
            'bash .github/scripts/setup-python.sh', 'python3 -m unittest discover -v',
            'exec python3 .github/scripts/sandbox-experiment.py --output uf-sandbox-experiment.json'])
        self.assertNotIn('environment', job)
        self.assertNotIn('secrets', str(config))
        for step in (job['steps'][0], job['steps'][-1]):
            self.assertRegex(step['uses'], r'@[0-9a-f]{40}$')

    def test_external_boundary_aba_is_reversible_same_runtime_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / 'trace'
            helper = root / 'privileged-standin.py'
            helper.write_text('''import json, sys
from pathlib import Path
trace = Path(sys.argv[1])
for line in sys.stdin:
    action = json.loads(line)['action']
    with trace.open('a') as stream: stream.write(action + '\\n')
    if action == 'stage': result = {'ok': True, 'runtime': '/opt/perito-uf-sandbox-' + 'a'*32 + '/runtime', 'tree_sha256': 'b'*64}
    elif action == 'cleanup': result = {'ok': True, 'profile_removed': True, 'runtime_removed': True, 'processes_stopped': True}
    else: result = {'ok': True}
    print(json.dumps(result), flush=True)
''')
            observer = root / 'observer.py'
            observer.write_text('''import json, sys
from pathlib import Path
trace = Path(sys.argv[1])
phase = trace.read_text().splitlines().count('load') - trace.read_text().splitlines().count('unload')
record = {'outcome': 'ready' if phase else 'early_exit', 'launched': True,
'port_file_seen': bool(phase), 'port_alive': bool(phase), 'readiness': bool(phase),
'stderr_classes': ['none'] if phase else ['sandbox_refusal', 'crash'],
'stderr_truncated': False, 'exit_code': 0 if phase else None,
'signal': None if phase else 'SIGABRT',
'cleanup': {'process_group_stopped': True, 'owned_directory_removed': True}}
print(json.dumps([record]*3))
''')
            result = api().experiment([sys.executable, str(helper), str(trace)],
                                      [sys.executable, str(observer), str(trace)])
            self.assertEqual(result['status'], 'reversible_effect')
            self.assertEqual(list(result['phases']), ['A1', 'B', 'A2'])
            self.assertEqual(trace.read_text().splitlines(), ['stage', 'load', 'unload', 'cleanup'])
            self.assertTrue(all(result['cleanup'].values()))
            self.assertNotIn('/opt/', json.dumps(result))

    def test_failed_observer_cannot_supply_success_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owner = root / 'owner.py'
            owner.write_text('''import json, sys
for line in sys.stdin:
 action = json.loads(line)['action']
 if action == 'stage': result = {'ok': True, 'runtime': '/opt/perito-uf-sandbox-'+'a'*32+'/runtime', 'tree_sha256': 'b'*64}
 elif action == 'cleanup': result = {'ok': True, 'profile_removed': True, 'runtime_removed': True, 'processes_stopped': True}
 else: result = {'ok': True}
 print(json.dumps(result), flush=True)
''')
            observer = root / 'observer.py'
            observer.write_text('''import json
record = {'outcome':'ready','launched':True,'port_file_seen':True,'port_alive':True,
'readiness':True,'stderr_classes':['none'],'stderr_truncated':False,'exit_code':0,
'signal':None,'cleanup':{'process_group_stopped':True,'owned_directory_removed':True}}
print(json.dumps([record]*3))
raise SystemExit(1)
''')
            result = api().experiment([sys.executable, str(owner)], [sys.executable, str(observer)])
            self.assertEqual(result['status'], 'experiment_failed')
            self.assertEqual(result['phases'], {})
            self.assertTrue(all(result['cleanup'].values()))

    def test_owned_tree_integrity_rejects_external_symlinks_and_privileged_modes(self):
        spec = importlib.util.spec_from_file_location('sandbox_owner', SCRIPT.with_name('sandbox-owner.py'))
        owner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(owner)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'runtime'
            root.mkdir()
            executable = root / 'chrome'
            executable.write_text('pinned bytes')
            executable.chmod(0o755)
            original = owner.tree_inventory(root)
            (root / 'link').symlink_to('chrome')
            self.assertNotEqual(owner.tree_inventory(root), original)
            (root / 'link').unlink()
            executable.write_text('different bytes')
            self.assertNotEqual(owner.tree_inventory(root), original)
            (root / 'link').symlink_to('../outside')
            (root.parent / 'outside').touch()
            with self.assertRaises(ValueError):
                owner.tree_inventory(root)
            (root / 'link').unlink()
            executable.chmod(0o4755)
            with self.assertRaises(ValueError):
                owner.tree_inventory(root)
            with self.assertRaises(ValueError):
                owner.protected_ancestors(root)
        name = 'perito-uf-sandbox-' + 'a'*32
        policy = owner.policy_text(name, Path('/opt') / name / 'runtime/chrome-linux64/chrome')
        self.assertIn('abi <abi/4.0>,', policy)
        self.assertIn('flags=(unconfined)', policy)
        self.assertIn('  userns,', policy)
        self.assertNotIn('*', policy)
        with self.assertRaises(ValueError):
            owner.policy_text(name, Path('/tmp/chrome'))
        with self.assertRaises(ValueError):
            owner.policy_text('chrome*', Path('/tmp/chrome'))

    def test_untrusted_local_cli_never_starts_privileged_operations(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--output', '/unused'],
                                env={**os.environ, 'GITHUB_REPOSITORY': 'other/repo'},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, '[DEBUG-uf-linux] trusted ephemeral manual main required\n')
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
