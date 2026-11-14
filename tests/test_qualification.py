"""Public read-only qualification command with OFFLINE external process documents."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/uf'


class QualificationTests(unittest.TestCase):
    def test_command_retains_two_fresh_raw_exports_and_only_sanitized_aggregate_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'external-runtime'
            runtime.write_text('#!' + sys.executable + '\nimport runpy\nrunpy.run_path(' +
                               repr(str(ROOT / 'tests/uf_runtime.py')) + ", run_name='__main__')\n")
            runtime.chmod(0o700)
            sequence = root / 'sequence.json'
            sequence.write_text(json.dumps([
                {'workbook': str(FIXTURES / f'run-{run}.xlsx'), 'evidence': str(FIXTURES / f'run-{run}.json')}
                for run in (6, 7)
            ]))
            env = {**os.environ, 'PERITO_NODE': str(runtime), 'PERITO_CHROME': sys.executable,
                   'PERITO_TEST_EXPORT_SEQUENCE': str(sequence)}
            output = root / 'proof'
            result = subprocess.run([sys.executable, '-m', 'perito_dashboard.qualify', '--output', str(output)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            proof = json.loads((output / 'proof.json').read_text())
            self.assertEqual(len(proof['exports']), 2)
            self.assertEqual(proof['exports'][0]['snapshot']['reference_month'], '2026-09')
            self.assertEqual(proof['exports'][0]['snapshot']['total'], 1108)
            self.assertEqual(proof['exports'][0]['snapshot']['semantic_identity'],
                             proof['exports'][1]['snapshot']['semantic_identity'])
            self.assertNotEqual(proof['exports'][0]['snapshot']['source']['sha256'],
                                proof['exports'][1]['snapshot']['source']['sha256'])
            for index, run in enumerate((6, 7), 1):
                self.assertEqual((output / f'export-{index}.xlsx').read_bytes(),
                                 (FIXTURES / f'run-{run}.xlsx').read_bytes())
                self.assertEqual(proof['exports'][index - 1]['cleanup'],
                                 {'browser_stopped': True, 'clean_profile_removed': True,
                                  'node_stopped': True, 'owned_directory_removed': True})
            self.assertEqual(proof['pins']['node']['version'], 'v26.13.1')
            self.assertIn('collector/runtime.json', proof['resources_sha256'])
            self.assertNotIn(str(root), json.dumps(proof))
            text = (output / 'proof.json').read_text()
            for forbidden in ('tempcontent', 'controlled-test-token', 'control.json', 'selectionTrace', 'webSocketDebuggerUrl'):
                self.assertNotIn(forbidden, text)
            self.assertFalse((root / 'data').exists())
            self.assertFalse((root / 'site').exists())

    def test_denial_unclean_export_and_reused_guid_produce_no_proof_or_retries(self):
        for case in ('denial', 'cleanup', 'guid', 'overlap'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                runtime = root / 'external-runtime'
                runtime.write_text('#!' + sys.executable + '\nimport runpy\nrunpy.run_path(' +
                                   repr(str(ROOT / 'tests/uf_runtime.py')) + ", run_name='__main__')\n")
                runtime.chmod(0o700)
                evidence = json.loads((FIXTURES / 'run-7.json').read_text())
                first = json.loads((FIXTURES / 'run-6.json').read_text())
                if case == 'denial':
                    for event in evidence['trace']:
                        if event['kind'] == 'ws_handshake':
                            event['status'] = 403
                elif case == 'guid':
                    guid = next(e['guid'] for e in first['trace'] if 'guid' in e)
                    for event in evidence['trace']:
                        if 'guid' in event:
                            event['guid'] = guid
                elif case == 'overlap':
                    # Each export is individually valid but their owned sessions overlap.
                    evidence['trace'][0]['utc'] = first['trace'][0]['utc']
                (root / 'second.json').write_text(json.dumps(evidence))
                sequence = root / 'sequence.json'
                second = {'workbook': str(FIXTURES / 'run-7.xlsx'), 'evidence': str(root / 'second.json')}
                if case == 'cleanup':
                    second['cleanup'] = {'fatal': None, 'browser_stopped': False, 'clean_profile_removed': False}
                sequence.write_text(json.dumps([
                    {'workbook': str(FIXTURES / 'run-6.xlsx'), 'evidence': str(FIXTURES / 'run-6.json')}, second
                ]))
                env = {**os.environ, 'PERITO_NODE': str(runtime), 'PERITO_CHROME': sys.executable,
                       'PERITO_TEST_EXPORT_SEQUENCE': str(sequence)}
                output = root / 'proof'
                result = subprocess.run([sys.executable, '-m', 'perito_dashboard.qualify', '--output', str(output)],
                                        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn('UF qualification failed:', result.stderr)
                self.assertFalse(output.exists())
                self.assertEqual(sequence.with_suffix('.count').read_text(), '2')
                self.assertFalse(list(root.glob('.uf-proof-*')))
                for line in sequence.with_suffix('.runs').read_text().splitlines():
                    owned = json.loads(line)
                    self.assertFalse(Path(owned['run']).parent.exists())
                    with self.assertRaises(ProcessLookupError):
                        os.kill(owned['pid'], 0)


if __name__ == '__main__':
    unittest.main()
