"""Manual read-only observation of the SAME self-validating live UF source.

No site/data mutation, fixture input, source override, or qualification switch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from ._collector import OfficialUF, _runtime


def _resources_sha256():
    root = Path(__file__).resolve().parent
    names = ('_collector.py', '_uf.py', 'runtime.py', 'qualify.py',
             'collector/browser-probe.mjs', 'collector/collect-flow.js', 'collector/runtime.json')
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New aggregate-only proof directory')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output must not already exist')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        hashes = _resources_sha256()
        collector = OfficialUF()
        collector.latest_export()
        if hashes != _resources_sha256():
            raise ValueError('UF collector resources changed during observation')
        if os.environ.get('PERITO_RUNTIME_ROOT'):
            runtime = Path(os.environ['PERITO_RUNTIME_ROOT'])
            node, chrome = str(runtime / 'node/bin/node'), str(runtime / 'chrome-linux64/chrome')
        else:
            node = _runtime('PERITO_NODE', ['node'])
            chrome = _runtime('PERITO_CHROME', ['google-chrome', 'chromium', 'chromium-browser',
                              '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'])
        node_version = subprocess.run([node, '--version'], capture_output=True, text=True,
                                      check=True, timeout=10).stdout.strip()
        proof = {
            'runtime': {'python': platform.python_version(), 'node': node_version,
                        'system': platform.system(), 'machine': platform.machine(),
                        'runner_image': os.environ.get('ImageVersion'),
                        'runner_os': os.environ.get('ImageOS')},
            'resources_sha256': hashes,
            'pins': json.loads((Path(__file__).resolve().parent / 'collector/runtime.json').read_text()),
            'executables_sha256': {name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                                   for name, path in (('python', sys.executable), ('node', node), ('chrome', chrome))},
            'exports': [],
        }
        # Only explicitly selected safe aggregate fields, never frontend trace,
        # cookies, auth/control tokens, temporary URLs, raw browser logs or profiles.
        with tempfile.TemporaryDirectory(prefix='.uf-proof-', dir=args.output.parent) as directory:
            stage = Path(directory) / 'proof'
            stage.mkdir()
            for index, (export, snapshot) in enumerate(collector.proof, 1):
                (stage / f'export-{index}.xlsx').write_bytes(export.content)
                proof['exports'].append({
                    'snapshot': snapshot,
                    'browser_version': export.evidence['browser_version'],
                    'cleanup': {key: export.evidence['cleanup'][key] for key in
                                ('browser_stopped', 'clean_profile_removed', 'node_stopped', 'owned_directory_removed')},
                    'events': [{key: event[key] for key in
                                ('kind', 'utc', 'guid', 'status', 'cookieCountBeforeNavigation',
                                 'state', 'receivedBytes', 'totalBytes') if key in event}
                               for event in export.evidence['trace'] if event['kind'] in
                               ('isolation', 'ws_handshake', 'Browser.downloadWillBegin', 'Browser.downloadProgress')],
                })
            (stage / 'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
            stage.rename(args.output)
        print('Two independent aggregate exports agree; proof retained. This is an observation, not issue closure.')
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'UF qualification failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
