"""[DEBUG-uf-linux] Temporary no-Gov causal probe, never source qualification."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from perito_dashboard.runtime import MANIFEST, ensure_runtime  # noqa: E402

spec = importlib.util.spec_from_file_location('linux_diagnosis', Path(__file__).with_name('diagnose-uf-linux.py'))
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)
OWNED_ROOT = r'/usr/lib/perito-uf-sandbox-[0-9a-f]{32}/runtime'
OWNER_FAILURE_REASONS = frozenset({
    'ancestor_unprotected', 'source_ownership', 'collision', 'inventory_refused',
    'copy_integrity', 'executable_integrity', 'policy_refused', 'parser_untrusted',
    'not_staged', 'runtime_changed', 'process_visibility', 'browser_running',
    'policy_removal', 'policy_absent', 'invalid_request', 'interrupted', 'unexpected_error',
})


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def validated_owner_final(response, action):
    """Validate the entire bounded receipt before retaining ANY cleanup/failure facts."""
    cleanup_keys = {'profile_removed', 'runtime_removed', 'processes_stopped'}
    if not isinstance(response, dict) or response.get('ok') is not True:
        raise ValueError('owner final')
    expected = {'ok', *cleanup_keys}
    if 'failure' in response:
        expected |= {'failure', 'candidate_ancestors'}
        failure = response['failure']
        if (not isinstance(failure, dict) or set(failure) != {'action', 'reason'}
                or not isinstance(failure['action'], str) or failure['action'] not in {action, 'protocol'}
                or not isinstance(failure['reason'], str) or failure['reason'] not in OWNER_FAILURE_REASONS):
            raise ValueError('owner failure')
        candidates = response.get('candidate_ancestors')
        if not isinstance(candidates, dict) or set(candidates) != {'root', 'opt', 'usr', 'usr_lib'}:
            raise ValueError('owner candidates')
        for facts in candidates.values():
            if (not isinstance(facts, dict)
                    or set(facts) != {'directory', 'non_symlink', 'root_owned', 'group_or_world_writable'}
                    or any(value is not None and type(value) is not bool for value in facts.values())):
                raise ValueError('owner candidate facts')
    if set(response) != expected or any(type(response[key]) is not bool for key in cleanup_keys):
        raise ValueError('owner cleanup')
    return response


def trusted():
    return all(os.environ.get(key) == value for key, value in {
        'GITHUB_REPOSITORY': 'tiagoguerreirodev/monitorar-vacancias-perito-pf',
        'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
        'RUNNER_OS': 'Linux',
    }.items())


def host_facts():
    """Read-only supporting facts; null means unknown, not a diagnosis."""
    def number(path):
        try:
            with Path(path).open() as stream:
                text = stream.read(65).strip()
            return int(text) if re.fullmatch(r'[0-9]{1,12}', text) else None
        except OSError:
            return None
    def enabled(path):
        try:
            with Path(path).open() as stream:
                text = stream.read(17).strip()
            return {'Y': True, 'N': False}.get(text)
        except OSError:
            return None
    def available(path):
        try:
            return Path(path).stat().st_size >= 0
        except FileNotFoundError:
            return False
        except OSError:
            return None
    def userns_feature():
        try:
            with Path('/sys/kernel/security/apparmor/features/namespaces/mask').open() as stream:
                text = stream.read(1025)
            return 'userns_create' in text.split() if len(text) <= 1024 else None
        except OSError:
            return None
    return {
        'is_root': os.geteuid() == 0,
        'apparmor_enabled': enabled('/sys/module/apparmor/parameters/enabled'),
        'apparmor_restrict_unprivileged_userns': number('/proc/sys/kernel/apparmor_restrict_unprivileged_userns'),
        'unprivileged_userns_clone': number('/proc/sys/kernel/unprivileged_userns_clone'),
        'max_user_namespaces': number('/proc/sys/user/max_user_namespaces'),
        'policy_abi_available': available('/etc/apparmor.d/abi/4.0'),
        'parser_available': available('/sbin/apparmor_parser'),
        'userns_feature_available': userns_feature(),
    }


def red(records):
    return len(records) == 3 and all(
        item['outcome'] == 'early_exit' and item['signal'] == 'SIGABRT'
        and 'sandbox_refusal' in item['stderr_classes'] and not item['port_file_seen']
        and not item['readiness'] and item['launched'] for item in records)


def green(records):
    return len(records) == 3 and all(item['outcome'] == 'ready' and item['readiness']
                                   and item['launched'] and item['port_file_seen']
                                   and item['port_alive'] for item in records)


def experiment(privileged_command, observer_command):
    """External process seams only; reports never contain command output or paths."""
    result = {'status': 'unsupported', 'tree_sha256': None, 'phases': {},
              'cleanup': {'profile_removed': False, 'runtime_removed': False, 'processes_stopped': False}}
    owner = None
    owner_cleanup = None
    active = None
    interrupted = False
    previous = {}
    def interrupt(_signum, _frame):
        nonlocal interrupted
        interrupted = True
        if active is not None:
            try:
                os.killpg(active.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, interrupt)

    def request(action):
        nonlocal owner_cleanup
        recovering = False
        try:
            owner.stdin.write((json.dumps({'action': action}) + '\n').encode())
            owner.stdin.flush()
        except BrokenPipeError:
            if action != 'cleanup':
                raise
            # A final receipt may be unread when the owner closes its input.
            # Require EOF for the whole recovery receipt, within one second.
            recovering = True
        deadline = time.monotonic() + (1 if recovering else 180)
        data = b''
        while (recovering or b'\n' not in data) and len(data) <= 4096:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([owner.stdout], [], [], remaining)[0]:
                raise ValueError('owner deadline')
            block = os.read(owner.stdout.fileno(), 4097 - len(data))
            if not block:
                if recovering:
                    break
                raise ValueError('owner ended')
            data += block
        if len(data) > 4096 or not data.endswith(b'\n'):
            raise ValueError('owner report bound')
        try:
            response = json.loads(data, object_pairs_hook=unique_object)
        except RecursionError:
            raise ValueError('owner report nesting') from None
        if not isinstance(response, dict) or response.get('ok') is not True:
            raise ValueError('owner refused')
        if action == 'cleanup' or 'failure' in response or set(response) == {'ok', *result['cleanup']}:
            final = validated_owner_final(response, action)
            owner_cleanup = final
            if 'failure' in final:
                result['status'] = 'experiment_failed'
                result['owner_failure'] = final['failure']
                result['candidate_ancestors'] = final['candidate_ancestors']
            if action != 'cleanup':
                raise ValueError('owner entered finally')
        if action in {'load', 'unload'} and set(response) != {'ok'}:
            raise ValueError('owner transition failed')
        return response

    def observe(runtime):
        nonlocal active
        with tempfile.TemporaryFile() as output:
            active = subprocess.Popen([*observer_command, runtime], stdout=output,
                                      stderr=subprocess.DEVNULL, start_new_session=True,
                                      env={**os.environ, 'TMPDIR': str(Path(runtime).parent / 'p')})
            try:
                active.wait(timeout=105)
                if active.returncode:
                    raise ValueError('observation failed')
            except subprocess.TimeoutExpired:
                os.killpg(active.pid, signal.SIGTERM)
                try:
                    active.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(active.pid, signal.SIGKILL)
                    active.wait(timeout=5)
                raise ValueError('observation deadline') from None
            finally:
                active = None
            output.seek(0)
            records = diagnostic.validated_observations(output.read(16385).decode('utf-8'))
        if not all(all(item['cleanup'].values()) for item in records):
            raise ValueError('observation cleanup')
        return records

    try:
        owner = subprocess.Popen(privileged_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        staged = request('stage')
        runtime = staged.get('runtime', '')
        tree_hash = staged.get('tree_sha256', '')
        if (set(staged) != {'ok', 'runtime', 'tree_sha256'} or not isinstance(runtime, str)
                or not re.fullmatch(OWNED_ROOT, runtime) or not isinstance(tree_hash, str)
                or not re.fullmatch(r'[0-9a-f]{64}', tree_hash)):
            raise ValueError('stage report')
        result['tree_sha256'] = tree_hash
        if interrupted:
            result['status'] = 'interrupted'
            return result
        result['phases']['A1'] = observe(runtime)
        if interrupted:
            result['status'] = 'interrupted'
        elif not red(result['phases']['A1']):
            result['status'] = 'baseline_not_reproduced'
        else:
            request('load')
            if interrupted:
                result['status'] = 'interrupted'
            else:
                result['phases']['B'] = observe(runtime)
                request('unload')
                if interrupted:
                    result['status'] = 'interrupted'
                else:
                    result['phases']['A2'] = observe(runtime)
                    result['status'] = ('reversible_effect' if green(result['phases']['B'])
                                        and red(result['phases']['A2']) else 'no_reversible_effect')
    except (ValueError, OSError, subprocess.SubprocessError, UnicodeError):
        result['status'] = 'interrupted' if interrupted else 'experiment_failed'
    finally:
        if owner is not None:
            try:
                cleanup = owner_cleanup if owner_cleanup is not None else request('cleanup')
                result['cleanup'] = {key: cleanup[key] for key in result['cleanup']}
            except (ValueError, OSError, subprocess.SubprocessError, UnicodeError):
                pass
            finally:
                try:
                    owner.stdin.close()  # EOF also triggers the privileged owner's finally.
                except OSError:
                    pass
                try:
                    owner.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    # Never kill a privileged owner while it may be cleaning policy.
                    result['status'] = 'cleanup_failed'
                owner.stdout.close()
        if not all(result['cleanup'].values()):
            result['status'] = 'cleanup_failed'
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return result


def main():
    if not trusted() or os.geteuid() == 0:
        print('[DEBUG-uf-linux] trusted ephemeral manual main required', file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--observe', type=Path)
    args = parser.parse_args()
    if args.observe is not None:
        if not re.fullmatch(OWNED_ROOT, str(args.observe)):
            return 1
        pins = json.loads(MANIFEST.read_text())
        executables = {'python': sys.executable, 'node': str(args.observe / 'node/bin/node'),
                       'chrome': str(args.observe / 'chrome-linux64/chrome')}
        before = diagnostic.receipt(executables, pins)
        records = diagnostic.observations(executables['node'], executables['chrome'], pins['chrome']['version'])
        if before != diagnostic.receipt(executables, pins):
            return 1
        print(json.dumps(records))
        return 0
    if args.output is None or args.output.exists() or args.output.is_symlink():
        return 1
    report = {'schema_version': 1, 'tag': '[DEBUG-uf-linux]', 'scope': 'about_blank_only',
              'qualification': False, 'status': 'unsupported', 'provenance': {}, 'runtime': {},
              'resources_sha256': {}, 'host_before': host_facts(), 'host_after': {},
              'global_facts_unchanged': False, 'experiment': None}
    for key, env, pattern in [('code_revision', 'GITHUB_SHA', r'[0-9a-f]{40}'),
                              ('run_id', 'GITHUB_RUN_ID', r'[0-9]{1,20}'),
                              ('run_attempt', 'GITHUB_RUN_ATTEMPT', r'[0-9]{1,5}')]:
        value = os.environ.get(env, '')
        if not re.fullmatch(pattern, value):
            return 1
        report['provenance'][key] = value
    for name, path in {'experiment': Path(__file__), 'privileged_owner': Path(__file__).with_name('sandbox-owner.py'),
                       'diagnostic_driver': Path(diagnostic.__file__), 'startup_helper': diagnostic.HELPER,
                       'runtime_manifest': MANIFEST, 'runtime_installer': ROOT / 'perito_dashboard/runtime.py',
                       'production_launch_recipe': ROOT / 'perito_dashboard/collector/browser-probe.mjs'}.items():
        report['resources_sha256'][name] = diagnostic.digest(path)
    try:
        # No installation unless a separately reviewed, trusted runner has the support facts.
        facts = report['host_before']
        if (facts['apparmor_enabled'] is True and facts['apparmor_restrict_unprivileged_userns'] == 1
                and facts['policy_abi_available'] is True and facts['parser_available'] is True
                and type(facts['max_user_namespaces']) is int and facts['max_user_namespaces'] > 0
                and facts['unprivileged_userns_clone'] == 1
                and facts['userns_feature_available'] is True):
            source = Path(os.environ['PERITO_RUNTIME_ROOT']).absolute()
            node, chrome = ensure_runtime(source)
            pins = json.loads(MANIFEST.read_text())
            report['runtime']['before'] = diagnostic.receipt({'python': sys.executable, 'node': node, 'chrome': chrome}, pins)
            report['experiment'] = experiment(
                ['/usr/bin/sudo', '-n', '/usr/bin/python3', '-I', str(Path(__file__).with_name('sandbox-owner.py')),
                 str(source), str(os.getuid()), str(os.getgid())],
                [sys.executable, str(Path(__file__)), '--observe'])
            report['runtime']['after'] = diagnostic.receipt({'python': sys.executable, 'node': node, 'chrome': chrome}, pins)
            report['status'] = report['experiment']['status']
            if report['runtime']['before'] != report['runtime']['after']:
                report['status'] = 'runtime_changed'
    except (ValueError, OSError, subprocess.SubprocessError, KeyError):
        report['status'] = 'setup_failed'
    report['host_after'] = host_facts()
    report['global_facts_unchanged'] = report['host_before'] == report['host_after']
    if not report['global_facts_unchanged']:
        report['status'] = 'host_facts_changed'
    with args.output.open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print('[DEBUG-uf-linux] sanitized causal probe retained; no qualification')
    return 0 if report['experiment'] is None or all(report['experiment']['cleanup'].values()) else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError):
        print('[DEBUG-uf-linux] probe failed safely', file=sys.stderr)
        raise SystemExit(1)
