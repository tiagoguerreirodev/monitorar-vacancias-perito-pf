"""Protected-runtime transport and lifecycle. No checkout assets or local elevation.

The environment guard prevents accidental use, not forged-env authorization: sudo
remains the OS boundary. The owner accepts no destination, policy or binary input.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import platform
import re
import select
import shutil
import signal
import subprocess
import sys
import time

from .runtime import MANIFEST, UFBlocked, UFRuntimeError, UFRuntimeIntegrityError, _digest, ensure_runtime

OWNER = MANIFEST.with_name('runtime-owner.py')
OWNED_ROOT = r'/usr/lib/perito-uf-sandbox-[0-9a-f]{32}/runtime'
CLEANUP_KEYS = ('profile_removed', 'runtime_removed', 'processes_stopped')
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
    """Validate ALL fields before retaining any true OR false cleanup fact."""
    if not isinstance(response, dict) or response.get('ok') is not True:
        raise ValueError('owner final')
    expected = {'ok', *CLEANUP_KEYS}
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
    if set(response) != expected or any(type(response[key]) is not bool for key in CLEANUP_KEYS):
        raise ValueError('owner cleanup')
    return response


class OwnerClient:
    """One external owner, strict bounded protocol, cooperative cleanup and reaping."""
    def __init__(self, command):
        self.final = None
        self.exit_code = None
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, start_new_session=True)

    def request(self, action):
        if self.final is not None:
            raise ValueError('owner already ended')
        owner = self.process
        recovering = False
        try:
            owner.stdin.write((json.dumps({'action': action}) + '\n').encode())
            owner.stdin.flush()
            if action == 'cleanup':
                owner.stdin.close()  # No more requests; cooperative EOF also ends protocol fixtures.
        except BrokenPipeError:
            if action != 'cleanup':
                raise
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
        # Every final, including an early refusal, must be drained through EOF.
        # A valid first line followed by output or an inherited pipe is not proof.
        if action == 'cleanup' or recovering:
            data = self._drain(data)
        response = self._decode(data)
        final = (action == 'cleanup' or 'failure' in response
                 or set(response) == {'ok', *CLEANUP_KEYS})
        if final:
            if action != 'cleanup' and not recovering:
                data = self._drain(data)
                response = self._decode(data)
            self.final = validated_owner_final(response, action)
            if action != 'cleanup':
                raise ValueError('owner entered finally')
        elif action in {'load', 'unload'} and response != {'ok': True}:
            raise ValueError('owner transition failed')
        return response

    def _drain(self, data):
        deadline = time.monotonic() + 1
        while len(data) <= 4096:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise ValueError('owner final deadline')
            block = os.read(self.process.stdout.fileno(), 4097 - len(data))
            if not block:
                return data
            data += block
        raise ValueError('owner report bound')

    @staticmethod
    def _decode(data):
        if len(data) > 4096 or not data.endswith(b'\n'):
            raise ValueError('owner report bound')
        try:
            response = json.loads(data, object_pairs_hook=unique_object)
        except RecursionError:
            raise ValueError('owner report nesting') from None
        if not isinstance(response, dict) or response.get('ok') is not True:
            raise ValueError('owner refused')
        return response

    def finish(self):
        try:
            if self.final is None:
                self.request('cleanup')
        except (ValueError, OSError, UnicodeError):
            raise UFRuntimeError('UF protected owner receipt failed') from None
        finally:
            try:
                self.process.stdin.close()  # EOF enters owner's finally, even after bad protocol.
            except OSError:
                pass
            try:
                self.exit_code = self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                # Never kill the privileged owner while it may be removing policy.
                raise UFRuntimeError('UF protected owner cleanup deadline') from None
            finally:
                self.process.stdout.close()
        if (self.exit_code != 0 or self.final is None or 'failure' in self.final
                or not all(self.final[key] for key in CLEANUP_KEYS)):
            raise UFRuntimeError('UF protected owner cleanup failed')
        return {**{key: self.final[key] for key in CLEANUP_KEYS}, 'owner_exit': self.exit_code}


def trusted_runtime_context():
    repository = 'tiagoguerreirodev/monitorar-vacancias-perito-pf'
    expected = {'GITHUB_REPOSITORY': repository, 'GITHUB_REF': 'refs/heads/main',
                'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                'RUNNER_OS': 'Linux', 'ImageOS': 'ubuntu24'}
    workflow = os.environ.get('GITHUB_WORKFLOW_REF')
    event = os.environ.get('GITHUB_EVENT_NAME')
    allowed = ((workflow == repository + '/.github/workflows/qualify-uf.yml@refs/heads/main'
                and event == 'workflow_dispatch')
               or (workflow == repository + '/.github/workflows/pages.yml@refs/heads/main'
                   and event in {'workflow_dispatch', 'schedule'}))
    return (allowed and all(os.environ.get(key) == value for key, value in expected.items())
            and platform.system() == 'Linux' and platform.machine() == 'x86_64'
            and os.geteuid() != 0)


def preflight_paths(temporary, profile):
    """Pinned Linux singleton suffixes, full UTF-8 paths, excluding trailing NUL."""
    sizes = [len((str(temporary) + suffix).encode('utf-8')) for suffix in (
        '/org.chromium.Chromium.XXXXXX/SingletonSocket',
        '/com.google.Chrome.XXXXXX/SingletonSocket')]
    profile_size = len((str(profile) + '/SingletonSocket').encode('utf-8'))
    if any(size > 107 for size in [*sizes, profile_size]):
        raise UFRuntimeError('UF protected profile pathname exceeds Linux socket budget')
    return {'singleton_socket_bytes': sizes, 'profile_socket_bytes': profile_size}


def observation(node, chrome):
    paths = {'python': str(Path(sys.executable).resolve()), 'node': node, 'chrome': chrome}
    def version(path):
        output = subprocess.run([path, '--version'], capture_output=True, text=True,
                                check=True, timeout=10).stdout.strip()
        if re.fullmatch(r'(?:v|Google Chrome(?: for Testing)? |Chromium |Python )[0-9]+(?:\.[0-9]+){2,3}', output):
            return output
        return 'unrecognized version output (not runtime qualification)'
    try:
        return {'sha256': {name: _digest(Path(path)) for name, path in paths.items()},
                'versions': {'python': platform.python_version(), 'node': version(node), 'chrome': version(chrome)}}
    except (OSError, subprocess.SubprocessError):
        raise UFRuntimeError('UF runtime observation failed') from None


def _local_executable(variable, candidates):
    configured = os.environ.get(variable)
    for name in ([configured] if configured else candidates):
        path = shutil.which(name)
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return str(Path(path).resolve())
    raise UFBlocked('UF collector requires executable ' + variable)


@dataclass
class Capsule:
    node: str
    chrome: str
    temporary_parent: Path | None = None
    environment: dict = field(default_factory=lambda: dict(os.environ))
    receipt: dict | None = None

    def preflight_run(self, root):
        if self.temporary_parent is not None:
            # Python's empty-prefix TemporaryDirectory contributes eight characters;
            # Node's pinned p-XXXXXX layout is independently checked before launch.
            return preflight_paths(self.temporary_parent, Path(root) / 'run/p-XXXXXX')


def _check_pins(receipt):
    pins = json.loads(MANIFEST.read_text())
    for key in ('node', 'chrome'):
        if (receipt['sha256'][key] != pins[key]['executable_sha256']
                or pins[key]['version'] not in receipt['versions'][key].split()):
            raise UFRuntimeIntegrityError('UF protected executable does not match pins')
    if (receipt['versions']['python'] != pins['python']['version']
            or receipt['sha256']['python'] != pins['python']['executable_sha256']):
        raise UFRuntimeIntegrityError('UF protected Python executable does not match pin')


@contextmanager
def open_capsule():
    client = None
    previous = {}
    cleaning = False
    try:
        if os.environ.get('PERITO_RUNTIME_ROOT'):
            if not trusted_runtime_context():
                raise UFRuntimeError('UF protected runtime requires trusted hosted Ubuntu main workflow')
            source = Path(os.environ['PERITO_RUNTIME_ROOT']).absolute()
            ensure_runtime(source)
            client = OwnerClient(['/usr/bin/sudo', '-n', '/usr/bin/python3', '-I', str(OWNER),
                                  str(source), str(os.getuid()), str(os.getgid())])
            def interrupt(_signum, _frame):
                if not cleaning:
                    raise UFRuntimeError('UF protected runtime interrupted')
            for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
                previous[signum] = signal.signal(signum, interrupt)
            staged = client.request('stage')
            runtime, tree = staged.get('runtime'), staged.get('tree_sha256')
            if (set(staged) != {'ok', 'runtime', 'tree_sha256'} or not isinstance(runtime, str)
                    or not re.fullmatch(OWNED_ROOT, runtime) or not isinstance(tree, str)
                    or not re.fullmatch(r'[0-9a-f]{64}', tree)):
                raise UFRuntimeError('UF protected stage receipt failed')
            parent = Path(runtime).parent / 'p'
            capsule = Capsule(str(Path(runtime) / 'node/bin/node'),
                              str(Path(runtime) / 'chrome-linux64/chrome'), parent,
                              {**os.environ, 'TMPDIR': str(parent)})
            preflight_paths(parent, parent / 'xxxxxxxx/run/p-XXXXXX')
            before = observation(capsule.node, capsule.chrome)
            _check_pins(before)
            client.request('load')
        else:
            if os.geteuid() == 0:
                raise UFRuntimeError('UF browser must be unprivileged')
            capsule = Capsule(_local_executable('PERITO_NODE', ['node']),
                              _local_executable('PERITO_CHROME', ['google-chrome', 'chromium', 'chromium-browser',
                                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']))
            before = observation(capsule.node, capsule.chrome)
        yield capsule
        after = observation(capsule.node, capsule.chrome)
        if before != after:
            raise UFRuntimeIntegrityError('UF runtime changed during collection')
        receipt = {'before': before, 'after': after}
        if client is not None:
            _check_pins(after)
            verified = client.request('verify')
            if verified != {'ok': True, 'tree_sha256': tree}:
                raise UFRuntimeIntegrityError('UF protected runtime tree changed')
            receipt['protected_tree'] = {'before': tree, 'after': verified['tree_sha256']}
            cleaning = True
            receipt['capsule_cleanup'] = client.finish()
            client = None
        capsule.receipt = receipt  # Finalized only after owner exit and complete cleanup.
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise UFRuntimeError('UF runtime capsule failed') from None
    finally:
        cleaning = True
        try:
            if client is not None:
                client.finish()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
