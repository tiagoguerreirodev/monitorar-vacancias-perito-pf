"""External unprivileged protocol peers; not Linux/source qualification."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest

from perito_dashboard._capsule import OwnerClient
from perito_dashboard.runtime import UFRuntimeError, runtime_capsule
from tests.test_production_capsule import external_capsule
from tests.test_sandbox_experiment import api


STAGE = {
    'ok': True,
    'runtime': '/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime',
    'tree_sha256': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
}
FINAL = {'ok': True, 'profile_removed': True, 'runtime_removed': True,
         'processes_stopped': True}
CLEANUP = {'profile_removed': True, 'runtime_removed': True,
           'processes_stopped': True, 'owner_exit': 0}
PEER = r'''
import json, sys
from pathlib import Path
root, payload, early = Path(sys.argv[1]), sys.argv[2], sys.argv[3] == 'early'
owned = root / 'owned'
owned.mkdir()
for line in sys.stdin:
    action = json.loads(line)['action']
    with (root / 'events').open('a') as stream:
        stream.write(action + '\n')
    if action == 'stage':
        if early:
            owned.rmdir()
        print(payload, flush=True)
        if early:
            break
    elif action == 'cleanup':
        owned.rmdir()
        print('{"ok":true,"profile_removed":true,"runtime_removed":true,"processes_stopped":true}', flush=True)
        break
'''


def invalid_stages():
    for change in ({'extra': 'SECRET /private'}, {'ok': 1}, {'ok': False},
                   {'runtime': False}, {'runtime': []}, {'tree_sha256': 1},
                   {'tree_sha256': None}, {'tree_sha256': 'B' * 64},
                   {'tree_sha256': 'b' * 63}, {'tree_sha256': 'g' * 64},
                   {'tree_sha256': 'b' * 64 + '\n'},
                   {'runtime': '/tmp/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime'},
                   {'runtime': '/usr/lib/perito-uf-sandbox-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/runtime'},
                   {'runtime': '/usr/lib/perito-uf-sandbox-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/runtime'},
                   {'runtime': STAGE['runtime'] + '/extra'},
                   {'runtime': STAGE['runtime'] + '\n'}):
        yield json.dumps({**STAGE, **change})
    for missing in ('ok', 'runtime', 'tree_sha256'):
        yield json.dumps({key: value for key, value in STAGE.items() if key != missing})
    yield json.dumps(STAGE)[:-1] + ',"runtime":"/tmp/SECRET"}'
    yield '{"ok":true,"runtime":' + '[' * 1500 + ']' * 1500 + '}'


@contextmanager
def peer(payload, early=False):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        command = [sys.executable, '-c', PEER, str(root), payload, 'early' if early else 'normal']
        yield root, command


class OwnerStageProtocolTests(unittest.TestCase):
    def test_public_client_rejects_malformed_stage_but_still_cleans_and_reaps(self):
        for payload in invalid_stages():
            with self.subTest(payload=payload[:100]), peer(payload) as (root, command):
                client = OwnerClient(command)
                try:
                    with self.assertRaises(ValueError):
                        client.request('stage')
                finally:
                    self.assertEqual(client.finish(), CLEANUP)
                self.assertEqual((root / 'events').read_text().splitlines(), ['stage', 'cleanup'])
                self.assertFalse((root / 'owned').exists())
                self.assertEqual(client.process.returncode, 0)

    def test_oversized_stage_never_claims_cleanup_from_unread_output(self):
        with peer(json.dumps({**STAGE, 'extra': 'SECRET' * 800})) as (root, command):
            client = OwnerClient(command)
            with self.assertRaises(ValueError):
                client.request('stage')
            with self.assertRaises(UFRuntimeError):
                client.finish()
            self.assertIsNone(client.final)
            self.assertEqual(client.process.returncode, 0)
            self.assertEqual((root / 'events').read_text().splitlines(), ['stage', 'cleanup'])
            self.assertFalse((root / 'owned').exists())

    def test_exact_stage_is_returned_then_cleanup_is_complete(self):
        with peer(json.dumps(STAGE)) as (root, command):
            client = OwnerClient(command)
            try:
                self.assertEqual(client.request('stage'), STAGE)
                self.assertIsNone(client.final)
            finally:
                self.assertEqual(client.finish(), CLEANUP)
            self.assertEqual((root / 'events').read_text().splitlines(), ['stage', 'cleanup'])
            self.assertFalse((root / 'owned').exists())

    def test_early_final_is_whole_validated_drained_and_not_checked_as_stage(self):
        for payload, accepted in ((json.dumps(FINAL), True),
                                  (json.dumps({**FINAL, 'runtime_removed': 1}), False),
                                  (json.dumps(FINAL) + '\nSECRET /private', False)):
            with self.subTest(payload=payload), peer(payload, early=True) as (root, command):
                client = OwnerClient(command)
                with self.assertRaises(ValueError):
                    client.request('stage')
                if accepted:
                    self.assertEqual(client.final, FINAL)
                    self.assertEqual(client.finish(), CLEANUP)
                else:
                    self.assertIsNone(client.final)
                    with self.assertRaises(UFRuntimeError):
                        client.finish()
                self.assertEqual(client.process.returncode, 0)
                self.assertEqual((root / 'events').read_text().splitlines(), ['stage'])
                self.assertFalse((root / 'owned').exists())

    def test_production_caller_preserves_safe_stage_error_and_cleanup(self):
        fixtures = Path(__file__).resolve().parent / 'fixtures/uf'
        documents = [{'workbook': str(fixtures / ('run-' + number + '.xlsx')),
                      'evidence': str(fixtures / ('run-' + number + '.json'))}
                     for number in ('6', '7')]
        with tempfile.TemporaryDirectory() as directory:
            with external_capsule(Path(directory), documents, 'malformed') as boundary:
                with self.assertRaisesRegex(UFRuntimeError, '^UF protected stage receipt failed$'):
                    with runtime_capsule():
                        self.fail('malformed stage reached collection')
                self.assertEqual(boundary['events'].read_text().splitlines(), ['stage', 'cleanup'])
                self.assertFalse(boundary['mirror'].exists())
                self.assertFalse(boundary['sequence'].with_suffix('.count').exists())
                self.assertEqual([owner.returncode for owner in boundary['owners']], [0])

    def test_diagnostic_caller_rejects_stage_without_observation_or_secret_leak(self):
        for payload in (json.dumps({**STAGE, 'extra': 'SECRET /private'}),
                        json.dumps({**STAGE, 'tree_sha256': 'B' * 64})):
            with self.subTest(payload=payload), peer(payload) as (root, command):
                result = api().experiment(command, ['never-observe'])
                self.assertEqual(result['status'], 'experiment_failed')
                self.assertEqual(result['phases'], {})
                self.assertIsNone(result['tree_sha256'])
                self.assertEqual(result['cleanup'], {key: True for key in FINAL if key != 'ok'})
                self.assertEqual((root / 'events').read_text().splitlines(), ['stage', 'cleanup'])
                self.assertFalse((root / 'owned').exists())
                self.assertNotIn('SECRET', json.dumps(result))
                self.assertNotIn('/private', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
