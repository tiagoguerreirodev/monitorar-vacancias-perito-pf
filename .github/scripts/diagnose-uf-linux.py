"""[DEBUG-uf-linux] Retained trusted no-Gov startup diagnostic; not qualification."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from perito_dashboard.runtime import MANIFEST, ensure_runtime  # noqa: E402
from perito_dashboard._shared import file_digest as digest  # noqa: E402

HELPER = Path(__file__).with_name('uf-linux-startup.mjs')


def receipt(executables, pins):
    result = {}
    for name, executable in executables.items():
        sha256 = digest(executable)
        if sha256 != pins[name]['executable_sha256']:
            raise ValueError('integrity')
        if name == 'python':
            version = platform.python_version()
        else:
            completed = subprocess.run([executable, '--version'], capture_output=True, text=True,
                                       check=True, timeout=10)
            # Only the exact expected version can leave this private boundary.
            version = pins[name]['version']
            if version not in completed.stdout.split():
                raise ValueError('version')
        if version != pins[name]['version']:
            raise ValueError('version')
        result[name] = {'version': version, 'sha256': sha256}
    return result


def validated_observations(stdout):
    if len(stdout.encode('utf-8')) > 16384:
        raise ValueError('helper report bound')
    records = json.loads(stdout)
    if not isinstance(records, list) or not 1 <= len(records) <= 3:
        raise ValueError('helper report shape')
    boolean_fields = {'launched', 'port_file_seen', 'port_alive', 'readiness', 'stderr_truncated'}
    fields = boolean_fields | {'outcome', 'stderr_classes', 'exit_code', 'signal', 'cleanup'}
    outcomes = {'startup_timeout', 'spawn_failed', 'early_exit', 'invalid_port_file',
                'invalid_readiness', 'ready', 'owner_interrupted', 'helper_failed'}
    signals = {None, 'SIGTERM', 'SIGKILL', 'SIGABRT', 'SIGSEGV', 'SIGTRAP', 'SIGILL', 'SIGBUS', 'other'}
    classes = {'sandbox_refusal', 'missing_library', 'permission_denied', 'crash', 'other', 'none',
               'suid_helper_fatal', 'zygote_host_fatal', 'namespace_fatal', 'credentials_fatal',
               'seccomp_fatal', 'crashpad_fatal', 'profile_fatal', 'resource_fatal',
               'suid_bad_configuration', 'suid_missing', 'no_usable_sandbox',
               'profile_socket_create', 'profile_socket_path_length', 'profile_socket_dir_check',
               'profile_listen', 'profile_peer_reply'}
    for record in records:
        if not isinstance(record, dict) or set(record) != fields:
            raise ValueError('helper record shape')
        if any(type(record[key]) is not bool for key in boolean_fields):
            raise ValueError('helper boolean')
        if not isinstance(record['outcome'], str) or record['outcome'] not in outcomes:
            raise ValueError('helper outcome')
        if record['signal'] is not None and (
                not isinstance(record['signal'], str) or record['signal'] not in signals):
            raise ValueError('helper signal')
        code = record['exit_code']
        if code is not None and (type(code) is not int or not 0 <= code <= 255):
            raise ValueError('helper exit code')
        labels = record['stderr_classes']
        if (not isinstance(labels, list) or not 1 <= len(labels) <= len(classes)
                or any(not isinstance(label, str) or label not in classes for label in labels)
                or len(set(labels)) != len(labels)):
            raise ValueError('helper classification')
        cleanup = record['cleanup']
        if (not isinstance(cleanup, dict)
                or set(cleanup) != {'process_group_stopped', 'owned_directory_removed'}
                or any(type(value) is not bool for value in cleanup.values())):
            raise ValueError('helper cleanup')
    return records


def observations(node, chrome, version):
    process = subprocess.Popen([node, str(HELPER), chrome, version], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    previous = {}
    shutting_down = False
    def interrupt(_signum, _frame):
        if not shutting_down:
            raise KeyboardInterrupt
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, interrupt)
    try:
        stdout, _ = process.communicate(timeout=90)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        shutting_down = True
        # Node handles termination by stopping its currently owned Chrome group.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise ValueError('helper interrupted or deadline') from None
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    if process.returncode:
        raise ValueError('helper failed')
    return validated_observations(stdout)


def main():
    # Defense in depth: no runtime preparation for an untrusted/manual-non-main caller.
    if any(os.environ.get(key) != value for key, value in {
        'GITHUB_REPOSITORY': 'tiagoguerreirodev/monitorar-vacancias-perito-pf',
        'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
    }.items()):
        print('[DEBUG-uf-linux] trusted manual main context required', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        print('[DEBUG-uf-linux] output must be new', file=sys.stderr)
        return 1
    report = {'schema_version': 1, 'tag': '[DEBUG-uf-linux]', 'scope': 'about_blank_only',
              'status': 'runtime_setup_failed', 'runtime': {}, 'observations': [],
              'resources_sha256': {name: digest(path) for name, path in {
                  'startup_helper': HELPER, 'diagnostic_driver': Path(__file__),
                  'runtime_manifest': MANIFEST, 'runtime_installer': ROOT / 'perito_dashboard/runtime.py',
                  'capsule_client': ROOT / 'perito_dashboard/_capsule.py',
                  'packaged_owner': ROOT / 'perito_dashboard/collector/runtime-owner.py',
                  'production_launch_recipe': ROOT / 'perito_dashboard/collector/browser-probe.mjs',
              }.items()}}
    report['provenance'] = {}
    for name, key, pattern in [('code_revision', 'GITHUB_SHA', r'[0-9a-f]{40}'),
                               ('run_id', 'GITHUB_RUN_ID', r'[0-9]{1,20}'),
                               ('run_attempt', 'GITHUB_RUN_ATTEMPT', r'[0-9]{1,5}')]:
        value = os.environ.get(key, '')
        if re.fullmatch(pattern, value):
            report['provenance'][name] = value
    try:
        pins = json.loads(MANIFEST.read_text())
        # Same existing managed runtime location and verified installer as qualification.
        node, chrome = ensure_runtime(os.environ['PERITO_RUNTIME_ROOT'])
        executables = {'python': sys.executable, 'node': node, 'chrome': chrome}
        report['runtime']['before'] = receipt(executables, pins)
        report['status'] = 'helper_failed'
        report['observations'] = observations(node, chrome, pins['chrome']['version'])
        report['status'] = 'runtime_changed'
        report['runtime']['after'] = receipt(executables, pins)
        if report['runtime']['before'] == report['runtime']['after']:
            report['status'] = 'observed'
    except (ValueError, OSError, subprocess.SubprocessError, KeyError):
        # No exception text, browser output, runtime paths or download URLs are retained.
        pass
    try:
        with args.output.open('x') as stream:
            stream.write(json.dumps(report, indent=2) + '\n')
    except OSError:
        print('[DEBUG-uf-linux] artifact write failed', file=sys.stderr)
        return 1
    print('[DEBUG-uf-linux] sanitized diagnostic retained; no Gov request or qualification performed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
