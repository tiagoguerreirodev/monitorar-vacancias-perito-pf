"""[DEBUG-uf-linux] Offline process-boundary checks, NOT Linux/browser proof."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / '.github/scripts/uf-linux-startup.mjs'


class DiagnosticWorkflowTests(unittest.TestCase):
    def test_manual_main_repository_guard_read_only_and_single_sanitized_artifact(self):
        config = json.loads((ROOT / '.github/workflows/diagnose-uf-linux.yml').read_text())
        self.assertEqual(config['on'], {'workflow_dispatch': {}})
        self.assertEqual(config['permissions'], {'contents': 'read'})
        self.assertEqual(set(config['jobs']), {'diagnose'})
        job = config['jobs']['diagnose']
        self.assertEqual(job['if'], "${{ github.repository == 'tiagoguerreirodev/monitorar-vacancias-perito-pf' && github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch' }}")
        self.assertEqual(job['runs-on'], 'ubuntu-24.04')
        self.assertLessEqual(job['timeout-minutes'], 15)
        self.assertNotIn('permissions', job)
        self.assertNotIn('environment', job)
        steps = job['steps']
        self.assertEqual(steps[0]['with'], {'ref': '${{ github.sha }}', 'persist-credentials': False})
        self.assertEqual([step['run'] for step in steps if 'run' in step], [
            'bash .github/scripts/setup-python.sh', 'python3 -m unittest discover -v',
            'python3 .github/scripts/diagnose-uf-linux.py --output uf-linux-diagnosis.json'])
        self.assertEqual(steps[-1]['with']['path'], 'uf-linux-diagnosis.json')
        for step in steps:
            self.assertNotIn('secrets', str(step))
            self.assertNotIn('continue-on-error', step)
            self.assertNotIn('if', step)
        for step in (steps[0], steps[-1]):
            self.assertRegex(step['uses'], r'@[0-9a-f]{40}$')

    def test_helper_cli_refuses_untrusted_context_without_output_or_raw_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'diagnosis.json'
            for key, value in [('GITHUB_REPOSITORY', 'untrusted/fork'),
                               ('GITHUB_REF', 'refs/heads/other'),
                               ('GITHUB_EVENT_NAME', 'push')]:
                env = {**os.environ, 'GITHUB_REPOSITORY': 'tiagoguerreirodev/monitorar-vacancias-perito-pf',
                       'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_dispatch', key: value}
                result = subprocess.run([shutil.which('python3'), str(ROOT / '.github/scripts/diagnose-uf-linux.py'),
                                         '--output', str(output)], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, '[DEBUG-uf-linux] trusted manual main context required\n')
                self.assertFalse(output.exists())


class DiagnosticShutdownTests(unittest.TestCase):
    def shutdown_report(self, payload, repeat_signal=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'helper-started'
            executable = root / 'external-node'
            executable.write_text(f'#!{sys.executable}\n' + '''import os, signal, time
from pathlib import Path

def terminate(signum, frame):
    time.sleep(0.2)
    print(os.environ['REPORT'], flush=True)
    raise SystemExit(0)

signal.signal(signal.SIGTERM, terminate)
Path(os.environ['START_MARKER']).touch()
while True:
    time.sleep(0.01)
''')
            executable.chmod(0o755)
            driver = root / 'driver.py'
            driver.write_text(
                'import json, runpy\n'
                f'api = runpy.run_path({str(ROOT / ".github/scripts/diagnose-uf-linux.py")!r})\n'
                f'print(json.dumps(api["observations"]({str(executable)!r}, '
                '"/unused-chrome", "157.0.8103.78")))\n')
            process = subprocess.Popen([sys.executable, str(driver)], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True,
                                       env={**os.environ, 'REPORT': payload, 'START_MARKER': str(marker)})
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists(), 'external helper did not start')
                process.send_signal(signal.SIGTERM)
                if repeat_signal:
                    time.sleep(0.05)
                    process.send_signal(signal.SIGTERM)
                return process.communicate(timeout=15), process.returncode
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_cooperative_shutdown_retains_prior_observation_and_cleanup(self):
        completed = {
            'outcome': 'early_exit', 'launched': True, 'port_file_seen': False,
            'port_alive': False, 'readiness': False, 'stderr_classes': ['sandbox_refusal'],
            'stderr_truncated': False, 'exit_code': 23, 'signal': None,
            'cleanup': {'process_group_stopped': True, 'owned_directory_removed': True},
        }
        interrupted = {**completed, 'outcome': 'owner_interrupted', 'exit_code': None,
                       'signal': 'SIGTERM', 'stderr_classes': ['none']}
        expected = [completed, interrupted]
        for repeat_signal in (False, True):
            with self.subTest(repeat_signal=repeat_signal):
                (stdout, stderr), code = self.shutdown_report(json.dumps(expected), repeat_signal)
                self.assertEqual(code, 0, stderr)
                self.assertEqual(json.loads(stdout), expected)
                self.assertEqual(stderr, '')

    def test_cooperative_shutdown_rejects_unbounded_or_unvalidated_output(self):
        record = {
            'outcome': 'owner_interrupted', 'launched': True, 'port_file_seen': False,
            'port_alive': False, 'readiness': False, 'stderr_classes': ['none'],
            'stderr_truncated': False, 'exit_code': None, 'signal': 'SIGTERM',
            'cleanup': {'process_group_stopped': True, 'owned_directory_removed': True},
        }
        invalid = [
            '', 'SECRET raw browser output', '{}', '[]', json.dumps([record] * 4),
            json.dumps([record]) + ' ' * 16384,
        ]
        for changes in (
            {'raw_output': 'SECRET'}, {'outcome': 'SECRET'}, {'signal': 'SECRET'},
            {'stderr_classes': ['SECRET']}, {'stderr_classes': ['none'] * 5},
            {'cleanup': {**record['cleanup'], 'path': 'SECRET'}},
            {'cleanup': {'process_group_stopped': 1, 'owned_directory_removed': True}},
            {'readiness': 'SECRET'}, {'exit_code': True}, {'exit_code': 256},
        ):
            invalid.append(json.dumps([{**record, **changes}]))
        for index, payload in enumerate(invalid):
            with self.subTest(case=index):
                (stdout, stderr), code = self.shutdown_report(payload)
                self.assertNotEqual(code, 0)
                self.assertEqual(stdout, '')
                self.assertNotIn('SECRET', stderr)


@unittest.skipUnless(shutil.which('node'), 'Node required for offline process stand-ins')
class LinuxStartupTests(unittest.TestCase):
    def observe(self, body, timeout=1500):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chrome = root / 'external-chrome'
            chrome.write_text('#!/usr/bin/env node\n' + body)
            chrome.chmod(0o755)
            driver = root / 'driver.mjs'
            driver.write_text(
                f'import {{observeStartup}} from {json.dumps(HELPER.as_uri())};\n'
                f'console.log(JSON.stringify(await observeStartup({json.dumps(str(chrome))}, '
                f'"157.0.8103.78", {timeout})));\n')
            result = subprocess.run(['node', str(driver)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            return json.loads(result.stdout), result.stdout

    def test_startup_failure_is_classified_without_raw_output_and_owned_state_is_removed(self):
        observation, text = self.observe('''
console.error('No usable sandbox! SECRET /private/profile DevTools ws://127.0.0.1:54321/token');
process.exit(23);
''')
        self.assertEqual(observation['outcome'], 'early_exit')
        self.assertEqual(observation['stderr_classes'], ['sandbox_refusal'])
        self.assertEqual(observation['exit_code'], 23)
        self.assertFalse(observation['port_file_seen'])
        self.assertEqual(observation['cleanup'], {'process_group_stopped': True, 'owned_directory_removed': True})
        for forbidden in ('SECRET', '/private', 'DevTools', '54321', 'token', 'ws://'):
            self.assertNotIn(forbidden, text)

    def test_ready_blank_target_uses_exact_production_arguments_and_removes_profile(self):
        observation, text = self.observe('''
const fs = require('node:fs');
const args = process.argv.slice(2);
const profile = args[1].slice('--user-data-dir='.length);
if (JSON.stringify([args[0], ...args.slice(2)]) !== JSON.stringify([
  '--headless=new', '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
  '--no-first-run', '--no-default-browser-check', 'about:blank'])) process.exit(42);
const server = require('node:http').createServer((req, res) => {
  res.end(JSON.stringify(req.url === '/json/version'
    ? {Browser: 'Chrome/157.0.8103.78', webSocketDebuggerUrl: 'SECRET'}
    : [{type: 'page', url: 'about:blank', id: 'SECRET'}]));
});
server.listen(0, '127.0.0.1', () => {
  fs.writeFileSync(profile + '/DevToolsActivePort', server.address().port + '\\n/SECRET');
});
process.on('SIGTERM', () => {
  if (!fs.existsSync(profile)) process.exit(43);
  server.close(() => process.exit(0));
});
''')
        self.assertEqual(observation['outcome'], 'ready')
        self.assertTrue(observation['launched'])
        self.assertTrue(observation['port_file_seen'])
        self.assertTrue(observation['port_alive'])
        self.assertTrue(observation['readiness'])
        self.assertTrue(all(observation['cleanup'].values()))
        self.assertNotIn('SECRET', text)

    def test_sigterm_during_group_cleanup_stops_further_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'cleanup-started'
            launches = root / 'launches'
            chrome = root / 'external-chrome'
            chrome.write_text('''#!/usr/bin/env node
const fs = require('node:fs');
const profile = process.argv.find(x => x.startsWith('--user-data-dir=')).slice(16);
fs.appendFileSync(process.env.LAUNCHES, profile + '\\n');
const server = require('node:http').createServer((req, res) => res.end(JSON.stringify(
  req.url === '/json/version' ? {Browser: 'Chrome/157.0.8103.78'}
  : [{type: 'page', url: 'about:blank'}])));
server.listen(0, '127.0.0.1', () => fs.writeFileSync(
  profile + '/DevToolsActivePort', server.address().port + '\\n/unused'));
process.on('SIGTERM', () => {
  fs.writeFileSync(process.env.CLEANUP_MARKER, 'ready');
  setTimeout(() => process.exit(0), 500);
});
''')
            chrome.chmod(0o755)
            process = subprocess.Popen(['node', str(HELPER), str(chrome), '157.0.8103.78'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       env={**os.environ, 'LAUNCHES': str(launches),
                                            'CLEANUP_MARKER': str(marker)})
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists(), 'external Chrome never received cleanup TERM')
                process.send_signal(signal.SIGTERM)
                time.sleep(0.05)
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
            self.assertEqual(process.returncode, 0, stderr)
            observations = json.loads(stdout)
            self.assertEqual(observations[0]['outcome'], 'owner_interrupted')
            self.assertEqual(len(observations), 1)
            self.assertEqual(len(launches.read_text().splitlines()), 1)
            self.assertTrue(all(observations[0]['cleanup'].values()))
            self.assertFalse(Path(launches.read_text().strip()).exists())

    def test_bounded_hung_startup_is_killed_and_stderr_is_not_retained(self):
        observation, text = self.observe('''
process.on('SIGTERM', () => {});
console.error('SECRET'.repeat(20000));
setInterval(() => {}, 1000);
''', timeout=1200)
        self.assertEqual(observation['outcome'], 'startup_timeout')
        self.assertEqual(observation['signal'], 'SIGKILL')
        self.assertTrue(observation['stderr_truncated'])
        self.assertTrue(all(observation['cleanup'].values()))
        self.assertNotIn('SECRET', text)

    def test_live_tcp_port_without_http_is_not_browser_readiness(self):
        observation, _ = self.observe('''
const fs = require('node:fs');
const profile = process.argv.find(x => x.startsWith('--user-data-dir=')).split('=')[1];
const server = require('node:net').createServer(socket => socket.destroy());
server.listen(0, '127.0.0.1', () => {
  fs.writeFileSync(profile + '/DevToolsActivePort', server.address().port + '\\n/SECRET');
});
''')
        self.assertTrue(observation['port_alive'])
        self.assertFalse(observation['readiness'])
        self.assertEqual(observation['outcome'], 'startup_timeout')
        self.assertTrue(all(observation['cleanup'].values()))

    def test_port_alive_does_not_mean_valid_browser_readiness(self):
        observation, _ = self.observe('''
const fs = require('node:fs');
const profile = process.argv.find(x => x.startsWith('--user-data-dir=')).split('=')[1];
const server = require('node:http').createServer((req, res) => res.end('NOT JSON SECRET'));
server.listen(0, '127.0.0.1', () => {
  fs.writeFileSync(profile + '/DevToolsActivePort', server.address().port + '\\n/SECRET');
});
''')
        self.assertEqual(observation['outcome'], 'startup_timeout')
        self.assertTrue(observation['port_alive'])
        self.assertFalse(observation['readiness'])
        self.assertTrue(all(observation['cleanup'].values()))


if __name__ == '__main__':
    unittest.main()
