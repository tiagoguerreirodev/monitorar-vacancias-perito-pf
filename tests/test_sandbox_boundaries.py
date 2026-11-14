"""[DEBUG-uf-linux] External-command stand-ins only; no sudo or browser launch."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from tests.test_sandbox_experiment import api, SCRIPT

OWNER = '''import json, sys
from pathlib import Path
trace = Path(sys.argv[1])
mode = sys.argv[2]
for line in sys.stdin:
 action = json.loads(line)['action']
 with trace.open('a') as stream: stream.write(action + '\\n')
 if action == 'stage':
  result = {'ok': True, 'runtime': '/usr/lib/perito-uf-sandbox-'+'a'*32+'/runtime', 'tree_sha256': 'b'*64}
  if mode.startswith('runtime:'): result['runtime'] = mode.removeprefix('runtime:')
  if mode == 'collision': result = {'ok': False, 'raw': 'SECRET /private ws://token'}
  if mode == 'early_final':
   print(json.dumps({'ok': True, 'profile_removed': True, 'runtime_removed': True, 'processes_stopped': True}), flush=True)
   break
 elif action == 'cleanup':
  result = {'ok': True, 'profile_removed': mode != 'cleanup_failure', 'runtime_removed': True, 'processes_stopped': True}
 else:
  result = {'ok': mode != 'load_failure'}
 print(json.dumps(result), flush=True)
'''
OBSERVER = '''import json, sys, signal, time, os
from pathlib import Path
trace = Path(sys.argv[1])
mode = sys.argv[2]
with trace.open('a') as stream: stream.write('observe:' + sys.argv[-1] + '\\n')
# Inspect the real external-process environment independently of report fixtures.
temporary = os.environ['TMPDIR']
trace.with_suffix('.tmpdir.json').write_text(json.dumps({
 'path': temporary,
 'socket_bytes': [len((temporary + suffix).encode()) for suffix in (
  '/org.chromium.Chromium.XXXXXX/SingletonSocket',
  '/com.google.Chrome.XXXXXX/SingletonSocket')]}))
if temporary != str(Path(sys.argv[-1]).parent / 'p'):
 sys.exit(8)
if mode == 'interrupt':
 signal.signal(signal.SIGTERM, lambda *_: sys.exit(2))
 while True: time.sleep(0.01)
if mode == 'raw':
 print('SECRET /private ws://token')
 sys.exit(0)
ready = mode == 'green'
record = {'outcome':'ready' if ready else 'early_exit', 'launched':True,
'port_file_seen':ready,'port_alive':ready,'readiness':ready,
'stderr_classes':['none'] if ready else ['sandbox_refusal','crash'],
'stderr_truncated':False,'exit_code':0 if ready else None,
'signal':None if ready else 'SIGABRT',
'cleanup':{'process_group_stopped':mode != 'unclean','owned_directory_removed':True}}
print(json.dumps([record]*3))
'''


class BoundaryTests(unittest.TestCase):
    def run_case(self, owner_mode='normal', observer_mode='red'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owner = root / 'owner.py'
            observer = root / 'observer.py'
            trace = root / 'trace'
            owner.write_text(OWNER)
            observer.write_text(OBSERVER)
            result = api().experiment([sys.executable, str(owner), str(trace), owner_mode],
                                      [sys.executable, str(observer), str(trace), observer_mode])
            if trace.with_suffix('.tmpdir.json').exists():
                temporary = json.loads(trace.with_suffix('.tmpdir.json').read_text())
                self.assertEqual(temporary['socket_bytes'], [106, 102])
                self.assertTrue(all(size <= 107 for size in temporary['socket_bytes']))
                self.assertEqual(temporary['path'],
                                 '/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/p')
            return result, trace.read_text().splitlines()

    def test_only_exact_dedicated_namespace_can_reach_observation(self):
        for runtime in (
                '/opt/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime',
                '/usr/lib/jvm/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime',
                '/tmp/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime',
                '/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime',
                '/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime/extra'):
            with self.subTest(runtime=runtime):
                result, trace = self.run_case(owner_mode='runtime:' + runtime)
                self.assertEqual(result['status'], 'experiment_failed')
                self.assertIsNone(result['tree_sha256'])
                self.assertEqual(result['phases'], {})
                self.assertEqual(trace, ['stage', 'cleanup'])
                self.assertTrue(all(result['cleanup'].values()))
                self.assertNotIn(runtime, json.dumps(result))

    def test_early_owner_finally_receipt_is_preserved_without_advancing(self):
        result, trace = self.run_case(owner_mode='early_final')
        self.assertEqual(result['status'], 'experiment_failed')
        self.assertTrue(all(result['cleanup'].values()))
        self.assertEqual(trace, ['stage'])

    def test_nonreproduction_never_loads_policy(self):
        result, trace = self.run_case(observer_mode='green')
        self.assertEqual(result['status'], 'baseline_not_reproduced')
        self.assertEqual(list(result['phases']), ['A1'])
        self.assertEqual([line for line in trace if not line.startswith('observe:')], ['stage', 'cleanup'])

    def test_collision_and_load_failure_do_not_advance_or_leak_output(self):
        for mode in ('collision', 'load_failure'):
            result, trace = self.run_case(owner_mode=mode)
            self.assertEqual(result['status'], 'experiment_failed')
            self.assertNotIn('SECRET', json.dumps(result))
            self.assertNotIn('/private', json.dumps(result))
            self.assertNotIn('B', result['phases'])
            self.assertEqual(trace[-1], 'cleanup')

    def test_bad_output_or_browser_cleanup_stops_before_policy_load(self):
        for mode in ('raw', 'unclean'):
            result, trace = self.run_case(observer_mode=mode)
            self.assertEqual(result['status'], 'experiment_failed')
            self.assertEqual(result['phases'], {})
            self.assertNotIn('load', trace)
            self.assertEqual(trace[-1], 'cleanup')
            self.assertNotIn('SECRET', json.dumps(result))

    def test_cleanup_failure_cannot_be_success_and_red_b_is_not_attribution(self):
        result, trace = self.run_case(owner_mode='cleanup_failure')
        self.assertEqual(result['status'], 'cleanup_failed')
        self.assertFalse(result['cleanup']['profile_removed'])
        result, trace = self.run_case()
        self.assertEqual(result['status'], 'no_reversible_effect')
        paths = [line for line in trace if line.startswith('observe:')]
        self.assertEqual(len(paths), 3)
        self.assertEqual(len(set(paths)), 1)

    def test_repeated_interruption_runs_cleanup_without_new_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            owner = root / 'owner.py'
            observer = root / 'observer.py'
            trace = root / 'trace'
            driver = root / 'driver.py'
            owner.write_text(OWNER)
            observer.write_text(OBSERVER)
            driver.write_text('import runpy,json\n' + f'api=runpy.run_path({str(SCRIPT)!r})\n'
                              + f'print(json.dumps(api["experiment"]({[sys.executable, str(owner), str(trace), "normal"]!r}, '
                              + f'{[sys.executable, str(observer), str(trace), "interrupt"]!r})))\n')
            process = subprocess.Popen([sys.executable, str(driver)], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True)
            try:
                deadline = time.monotonic() + 5
                while (not trace.exists() or 'observe:' not in trace.read_text()) and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertIn('observe:', trace.read_text())
                process.send_signal(signal.SIGTERM)
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                result = json.loads(stdout)
                self.assertEqual(result['status'], 'interrupted')
                self.assertTrue(all(result['cleanup'].values()))
                self.assertEqual(trace.read_text().splitlines()[-1], 'cleanup')
                self.assertNotIn('load', trace.read_text().splitlines())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


if __name__ == '__main__':
    unittest.main()
