"""[DEBUG-uf-linux] Offline process-boundary checks, NOT Linux/browser proof."""
import json
import os
from pathlib import Path
import shutil
import select
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

    def test_public_receiver_accepts_only_extended_fixed_vocabulary(self):
        labels = ['sandbox_refusal', 'missing_library', 'permission_denied', 'crash',
                  'suid_helper_fatal', 'zygote_host_fatal', 'namespace_fatal',
                  'credentials_fatal', 'seccomp_fatal', 'crashpad_fatal',
                  'profile_fatal', 'resource_fatal', 'suid_bad_configuration',
                  'suid_missing', 'no_usable_sandbox', 'other', 'none',
                  'profile_socket_create', 'profile_socket_path_length',
                  'profile_socket_dir_check', 'profile_listen', 'profile_peer_reply']
        record = {
            'outcome': 'early_exit', 'launched': True, 'port_file_seen': False,
            'port_alive': False, 'readiness': False, 'stderr_classes': labels,
            'stderr_truncated': False, 'exit_code': 23, 'signal': None,
            'cleanup': {'process_group_stopped': True, 'owned_directory_removed': True},
        }
        (stdout, stderr), code = self.shutdown_report(json.dumps([record]))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout), [record])
        for invalid in (labels + ['SECRET'], ['credentials.cc'], ['credentials_fatal'] * 2,
                        ['seccomp_fatal', 1], ['unlisted_fatal'], ['profile_other'],
                        [], labels + ['profile_listen'], ['profile_listen', {}]):
            with self.subTest(labels=invalid):
                (stdout, stderr), code = self.shutdown_report(json.dumps([{**record, 'stderr_classes': invalid}]))
                self.assertNotEqual(code, 0)
                self.assertEqual(stdout, '')
                self.assertNotIn('SECRET', stderr)
                self.assertNotIn('credentials.cc', stderr)

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
            {'raw_output': 'SECRET'}, {'sourceLine': 314}, {'filename': 'SECRET'},
            {'message': 'SECRET'}, {'errno': 1}, {'path': 'SECRET'},
            {'outcome': 'SECRET'}, {'signal': 'SECRET'},
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

    def test_public_process_classifies_pinned_helper_literal_without_disclosing_stderr(self):
        observation, text = self.observe('''
process.stderr.write('[123:456:FATAL:sandbox/linux/suid/client/setuid_sandbox_host.cc:166] The SUID sandbox helper binary was found, but is not configured correctly. SECRET /private/chrome-sandbox\\n');
process.exit(23);
''')
        self.assertEqual(observation['stderr_classes'],
                         ['crash', 'suid_helper_fatal', 'suid_bad_configuration'])
        self.assertEqual(observation['outcome'], 'early_exit')
        self.assertFalse(observation['readiness'])
        self.assertTrue(all(observation['cleanup'].values()))
        for forbidden in ('SECRET', '/private', 'setuid_sandbox_host.cc', '123:456', 'configured'):
            self.assertNotIn(forbidden, text)

    def test_public_process_classifies_allowlisted_fatal_sites_and_specific_literals(self):
        # Pinned public instrumentation contracts, not reproduced Chrome failures.
        cases = [
            ('setuid_sandbox_host.cc', 'The SUID sandbox helper binary is missing:',
             ['crash', 'suid_helper_fatal', 'suid_missing']),
            ('zygote_host_impl_linux.cc', 'No usable sandbox!',
             ['sandbox_refusal', 'crash', 'zygote_host_fatal', 'no_usable_sandbox']),
            ('sandbox_linux.cc', 'EngageNamespaceSandboxInternal(from_zygote)',
             ['crash', 'namespace_fatal']),
            ('credentials.cc', 'SetGidAndUidMaps(gid, uid)', ['crash', 'credentials_fatal']),
            ('sandbox_bpf.cc', 'Kernel refuses to enable no-new-privs', ['crash', 'seccomp_fatal']),
            ('sandbox_bpf.cc', 'Kernel refuses to turn on BPF filters', ['crash', 'seccomp_fatal']),
            ('crashpad_linux.cc', 'client.StartHandler(', ['crash', 'crashpad_fatal']),
            ('process_singleton_posix.cc', 'Socket path too long: ',
             ['crash', 'profile_fatal', 'profile_socket_path_length']),
            ('process_singleton_posix.cc', 'Temp directory mode is not 700: ',
             ['crash', 'profile_fatal', 'profile_socket_dir_check']),
            ('resource_bundle.cc', 'failed to load pak file', ['crash', 'resource_fatal']),
        ]
        for site, literal, expected in cases:
            with self.subTest(site=site, literal=literal):
                message = f'[123:456:FATAL:public/source/{site}:321] {literal} SECRET /private/token\n'
                observation, text = self.observe(f'process.stderr.write({json.dumps(message)}); process.exit(23);')
                self.assertEqual(observation['stderr_classes'], expected)
                self.assertEqual(observation['exit_code'], 23)
                self.assertFalse(observation['readiness'])
                self.assertTrue(all(observation['cleanup'].values()))
                for forbidden in (site, literal, 'SECRET', '/private', '123:456'):
                    self.assertNotIn(forbidden, text)

    def test_public_process_classifies_five_profile_literals(self):
        # Public pinned literals only; no actual Chromium cause is asserted.
        cases = [
            ('socket() failed', 'profile_socket_create'),
            ('Socket path too long: ', 'profile_socket_path_length'),
            ('Temp directory mode is not 700: ', 'profile_socket_dir_check'),
            ('listen failed: ', 'profile_listen'),
            ('The other process returned unknown message: ', 'profile_peer_reply'),
        ]
        for literal, label in cases:
            with self.subTest(label=label):
                message = f'[FATAL:chrome/browser/process_singleton_posix.cc:999] {literal}SECRET /private/token\n'
                observation, text = self.observe(f'process.stderr.write({json.dumps(message)}); process.exit(23);')
                self.assertEqual(observation['stderr_classes'], ['crash', 'profile_fatal', label])
                self.assertFalse(observation['readiness'])
                self.assertTrue(all(observation['cleanup'].values()))
                for forbidden in ('SECRET', '/private', '.cc', literal):
                    self.assertNotIn(forbidden, text)

    def test_public_process_profile_pinned_line_fallback(self):
        cases = [
            (297, 'profile_socket_create'),
            (314, 'profile_socket_path_length'), (315, 'profile_socket_path_length'),
            (1052, 'profile_socket_dir_check'), (1053, 'profile_socket_dir_check'),
            (1054, 'profile_socket_dir_check'),
            (1088, 'profile_listen'), (1089, 'profile_listen'),
            (936, 'profile_peer_reply'), (937, 'profile_peer_reply'),
        ]
        for line, label in cases:
            for location in (f':{line}', f'({line})'):
                with self.subTest(location=location):
                    message = f'[FATAL:process_singleton_posix.cc{location}] Check failed: SECRET\n'
                    observation, text = self.observe(f'process.stderr.write({json.dumps(message)}); process.exit(23);')
                    self.assertEqual(observation['stderr_classes'], ['crash', 'profile_fatal', label])
                    self.assertTrue(all(observation['cleanup'].values()))
                    self.assertFalse(observation['readiness'])
                    self.assertNotIn('SECRET', text)
                    self.assertNotIn('.cc', text)

    def test_public_process_profile_gates_precedence_order_and_bound(self):
        literals = ['socket() failed', 'Socket path too long: ',
                    'Temp directory mode is not 700: ', 'listen failed: ',
                    'The other process returned unknown message: ']
        for literal in literals:
            cases = [
                (f'[FATAL:unknown.cc:314] {literal}SECRET', ['crash']),
                (f'[fatal:process_singleton_posix.cc:314] {literal}SECRET', ['crash']),
                (f'[FATAL:process_singleton_posix.cc:999] {literal.upper()}SECRET',
                 ['crash', 'profile_fatal']),
                (f'[FATAL:process_singleton_posix.cc:999] SECRET\n{literal}',
                 ['crash', 'profile_fatal']),
                (f'[FATAL:secret_process_singleton_posix.cc:314] {literal}SECRET', ['crash']),
            ]
            for message, expected in cases:
                with self.subTest(message=message):
                    observation, text = self.observe(f'process.stderr.write({json.dumps(message)}); process.exit(23);')
                    self.assertEqual(observation['stderr_classes'], expected)
                    self.assertTrue(all(observation['cleanup'].values()))
                    self.assertNotIn('SECRET', text)
                    self.assertNotIn('.cc', text)
        cases = [
            # A known literal wins over a conflicting pinned line on that record.
            ('[FATAL:process_singleton_posix.cc:314] listen failed: SECRET',
             ['crash', 'profile_fatal', 'profile_listen']),
            # Fallback is per record, not suppressed by a literal on another line.
            ('[FATAL:process_singleton_posix.cc:314] SECRET\n'
             '[FATAL:process_singleton_posix.cc:999] listen failed: SECRET',
             ['crash', 'profile_fatal', 'profile_socket_path_length', 'profile_listen']),
            ('[FATAL:process_singleton_posix.cc:999] SECRET', ['crash', 'profile_fatal']),
        ]
        for message, expected in cases:
            with self.subTest(message=message):
                observation, text = self.observe(f'process.stderr.write({json.dumps(message)}); process.exit(23);')
                self.assertEqual(observation['stderr_classes'], expected)
                self.assertNotIn('SECRET', text)
        message = ''.join(f'[FATAL:process_singleton_posix.cc:999] {literal}SECRET\n'
                          for literal in reversed(literals)) * 2
        observation, text = self.observe(f'process.stderr.write({json.dumps(message)}); process.exit(23);')
        self.assertEqual(observation['stderr_classes'], [
            'crash', 'profile_fatal', 'profile_socket_create', 'profile_socket_path_length',
            'profile_socket_dir_check', 'profile_listen', 'profile_peer_reply'])
        self.assertNotIn('SECRET', text)
        observation, text = self.observe(
            "process.stderr.write('x'.repeat(65536) + " + json.dumps(message) + ", () => process.exit(23));")
        self.assertEqual(observation['stderr_classes'], ['other'])
        self.assertTrue(observation['stderr_truncated'])
        self.assertTrue(all(observation['cleanup'].values()))
        self.assertNotIn('SECRET', text)

    def test_public_process_fatal_site_fallback_is_fixed_deduplicated_and_ordered(self):
        sites = ['resource_bundle.cc', 'process_singleton_posix.cc', 'crashpad_linux.cc',
                 'sandbox_bpf.cc', 'credentials.cc', 'sandbox_linux.cc',
                 'zygote_host_impl_linux.cc', 'setuid_sandbox_host.cc']
        message = ''.join(f'[FATAL:public/{site}:99] Check failed: UNLISTED_SECRET\n' for site in sites) * 2
        observation, text = self.observe(f'process.stderr.write({json.dumps(message)}); process.exit(23);')
        self.assertEqual(observation['stderr_classes'], [
            'crash', 'suid_helper_fatal', 'zygote_host_fatal', 'namespace_fatal',
            'credentials_fatal', 'seccomp_fatal', 'crashpad_fatal', 'profile_fatal', 'resource_fatal'])
        self.assertTrue(all(observation['cleanup'].values()))
        self.assertNotIn('UNLISTED_SECRET', text)
        for site in sites:
            self.assertNotIn(site, text)

    def test_public_process_unknown_or_unpaired_secret_stays_generic(self):
        messages = [
            '[FATAL:private_secret.cc:123] SECRET /private/token',
            '[FATAL:secret_credentials.cc:123] SECRET',
            '[ERROR:credentials.cc:123] SECRET',
            '[FATAL:unknown.cc:1] The SUID sandbox helper binary is missing:',
            '[FATAL:unknown.cc:1] SECRET\nsetuid_sandbox_host.cc The SUID sandbox helper binary is missing:',
        ]
        for message in messages:
            with self.subTest(message=message):
                observation, text = self.observe(f'process.stderr.write({json.dumps(message)}); process.exit(23);')
                self.assertEqual(observation['stderr_classes'], ['crash'] if 'FATAL:' in message else ['other'])
                self.assertTrue(all(observation['cleanup'].values()))
                self.assertNotIn('SECRET', text)
                self.assertNotIn('.cc', text)

    def test_public_process_fatal_after_stderr_prefix_bound_is_not_classified(self):
        message = '[FATAL:credentials.cc:1] SECRET SetGidAndUidMaps(gid, uid)'
        observation, text = self.observe(
            "process.stderr.write('x'.repeat(65536) + " + json.dumps(message) + ", () => process.exit(23));")
        self.assertEqual(observation['stderr_classes'], ['other'])
        self.assertTrue(observation['stderr_truncated'])
        self.assertTrue(all(observation['cleanup'].values()))
        self.assertNotIn('SECRET', text)

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
        # Listener startup is outside observeStartup's bounded deadline. Keep
        # both server and accepted sockets alive until explicit parent teardown.
        server = subprocess.Popen(['node', '-e', '''
const sockets = new Set();
const server = require('node:net').createServer(socket => {
  sockets.add(socket);
  socket.on('error', () => {});
  socket.on('close', () => sockets.delete(socket));
});
server.listen(0, '127.0.0.1', () => console.log(server.address().port));
process.stdin.once('data', () => {
  for (const socket of sockets) socket.destroy();
  server.close(() => process.exit(0));
});
'''], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(select.select([server.stdout], [], [], 5)[0], 'TCP listener acknowledgement missing')
            port = int(server.stdout.readline())
            self.assertGreater(port, 0)
            observation, _ = self.observe('''
const fs = require('node:fs');
const profile = process.argv.find(x => x.startsWith('--user-data-dir=')).split('=')[1];
fs.writeFileSync(profile + '/DevToolsActivePort', ''' + json.dumps(str(port) + '\n/SECRET') + ''');
setInterval(() => {}, 1000);
''')
            self.assertIsNone(server.poll(), 'TCP-only listener ended before explicit teardown')
        finally:
            if server.poll() is None:
                try:
                    server.communicate('stop\\n', timeout=5)
                except subprocess.TimeoutExpired:
                    server.terminate()
                    try:
                        server.communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.communicate()
            else:
                server.communicate()
        self.assertEqual(server.returncode, 0)
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
