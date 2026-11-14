"""[DEBUG-uf-linux] Ephemeral runner only. Own one protected tree and one policy.

JSON stdin protocol; EOF/signals always enter cleanup. Never run on a local host.
No shell, global policy changes, package installation, cache or shared chmod/chown.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import time

SANDBOX_PARENT = '/usr/lib'
PARSER = Path('/sbin/apparmor_parser')
PROFILES = Path('/sys/kernel/security/apparmor/profiles')
HANDLED_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM)
FAILURE_REASONS = frozenset({
    'ancestor_unprotected', 'source_ownership', 'collision', 'inventory_refused',
    'copy_integrity', 'executable_integrity', 'policy_refused', 'parser_untrusted',
    'not_staged', 'runtime_changed', 'process_visibility', 'browser_running',
    'policy_removal', 'policy_absent', 'invalid_request', 'interrupted', 'unexpected_error',
})


class Refusal(ValueError):
    """Only explicit owner refusals may become fixed public reason codes."""


def candidate_ancestors():
    """Fixed read-only lstat facts, not a destination choice or protection proof."""
    result = {}
    for label, path in [('root', '/'), ('opt', '/opt'), ('usr', '/usr'), ('usr_lib', '/usr/lib')]:
        facts = dict.fromkeys(('directory', 'non_symlink', 'root_owned', 'group_or_world_writable'))
        try:
            info = Path(path).lstat()
            facts = {'directory': stat.S_ISDIR(info.st_mode),
                     'non_symlink': not stat.S_ISLNK(info.st_mode),
                     'root_owned': info.st_uid == 0,
                     'group_or_world_writable': bool(info.st_mode & 0o022)}
        except OSError:
            pass
        result[label] = facts
    return result


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def protected_ancestors(path):
    """Refuse symlinks, writable ancestors, and non-root ownership; never repair."""
    for entry in [path, *path.parents]:
        info = entry.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022):
            raise Refusal('ancestor_unprotected')


def tree_inventory(root, protected=False):
    """Bounded filesystem seam, preserving only internal relative symlinks."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise Refusal('inventory_refused')
    items = []
    size = 0
    for path in [root, *sorted(root.rglob('*'))]:
        if len(items) > 50000:
            raise Refusal('inventory_refused')
        info = path.lstat()
        if info.st_mode & 0o6000:
            raise Refusal('inventory_refused')
        if protected and (info.st_uid != 0 or (not path.is_symlink() and info.st_mode & 0o022)):
            raise Refusal('inventory_refused')
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            if os.path.isabs(target) or not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise Refusal('inventory_refused')
            items.append([name, 'symlink', target])
        elif stat.S_ISDIR(info.st_mode):
            items.append([name, 'directory'])
        elif stat.S_ISREG(info.st_mode):
            size += info.st_size
            if size > 2_000_000_000:
                raise Refusal('inventory_refused')
            items.append([name, 'file', bool(info.st_mode & 0o111), digest(path)])
        else:
            raise Refusal('inventory_refused')
    return hashlib.sha256(json.dumps(items, separators=(',', ':')).encode()).hexdigest()


def policy_text(name, chrome):
    # Both values are generated here, not supplied by a workflow input.
    import re
    if not re.fullmatch(r'perito-uf-sandbox-[0-9a-f]{32}', name):
        raise Refusal('policy_refused')
    if str(chrome) != SANDBOX_PARENT + '/' + name + '/runtime/chrome-linux64/chrome':
        raise Refusal('policy_refused')
    return ('abi <abi/4.0>,\ninclude <tunables/global>\n\n'
            f'profile {name} "{chrome}" flags=(unconfined) {{\n  userns,\n}}\n')


class Owner:
    def __init__(self, source, uid, gid):
        self.source = Path(source)
        self.uid = uid
        self.gid = gid
        self.name = 'perito-uf-sandbox-' + secrets.token_hex(16)
        self.base = Path(SANDBOX_PARENT) / self.name
        self.runtime = self.base / 'runtime'
        self.policy = self.base / 'profile'
        self.profiles = self.base / 'p'
        self.created = False
        self.policy_owned = False
        self.tree_hash = None

    def loaded(self):
        with PROFILES.open('rb') as stream:
            content = stream.read(4_000_001)
        if len(content) > 4_000_000:
            raise Refusal('policy_refused')
        # Never retain or emit the profile list.
        return any(line.split(b' ', 1)[0] == self.name.encode() for line in content.splitlines())

    def parser(self, action):
        protected_ancestors(PARSER.resolve().parent)
        info = PARSER.resolve().stat()
        if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode):
            raise Refusal('parser_untrusted')
        subprocess.run([str(PARSER), '--config-file', '/dev/null', '-K', '-j1', action, str(self.policy)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True, timeout=20,
                       env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C'})

    def stage(self):
        protected_ancestors(Path(SANDBOX_PARENT))
        if self.source != self.source.resolve(strict=True) or self.source.stat().st_uid != self.uid:
            raise Refusal('source_ownership')
        if self.loaded() or self.base.exists() or self.base.is_symlink():
            raise Refusal('collision')
        original = tree_inventory(self.source)
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, HANDLED_SIGNALS)
        try:
            self.base.mkdir(mode=0o755)  # Exclusive mkdir: never replace a collision.
            self.created = True
        finally:
            # Deliver pending interruptions only after exclusive ownership is recorded.
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        shutil.copytree(self.source, self.runtime, symlinks=True)
        for entry in [*self.runtime.rglob('*'), self.runtime]:
            if not entry.is_symlink():
                mode = entry.stat().st_mode
                entry.chmod(0o555 if entry.is_dir() or mode & 0o111 else 0o444)
        protected_ancestors(self.runtime)
        copied = tree_inventory(self.runtime, protected=True)
        if copied != original or tree_inventory(self.source) != original:
            raise Refusal('copy_integrity')
        # Independently verify executable pins without executing anything as root.
        pins = json.loads((Path(__file__).resolve().parents[2] / 'perito_dashboard/collector/runtime.json').read_text())
        for key, relative in [('node', 'node/bin/node'), ('chrome', 'chrome-linux64/chrome')]:
            executable = self.runtime / relative
            if executable.is_symlink() or digest(executable) != pins[key]['executable_sha256']:
                raise Refusal('executable_integrity')
        self.tree_hash = copied
        with self.policy.open('x') as stream:
            stream.write(policy_text(self.name, self.runtime / 'chrome-linux64/chrome'))
        self.policy.chmod(0o444)
        # Writable Chrome profiles are a sibling, never an executable ancestor.
        self.profiles.mkdir(mode=0o700)
        os.chown(self.profiles, self.uid, self.gid, follow_symlinks=False)
        return {'ok': True, 'runtime': str(self.runtime), 'tree_sha256': copied}

    def validate(self):
        if not self.created or self.tree_hash is None:
            raise Refusal('not_staged')
        protected_ancestors(self.runtime)
        if tree_inventory(self.runtime, protected=True) != self.tree_hash:
            raise Refusal('runtime_changed')
        if self.policy.read_text() != policy_text(self.name, self.runtime / 'chrome-linux64/chrome'):
            raise Refusal('policy_refused')

    def own_processes(self):
        """Only processes executing this unique immutable runtime, never names/PIDs from input."""
        found = []
        for process in Path('/proc').iterdir():
            if not process.name.isdigit():
                continue
            try:
                if process.stat().st_uid != self.uid:
                    continue
                executable = (process / 'exe').readlink()
                if executable.is_relative_to(self.runtime):
                    found.append(int(process.name))
            except (FileNotFoundError, ProcessLookupError):
                continue
            except PermissionError:
                # Cannot prove absence: fail closed rather than delete under a live browser.
                raise Refusal('process_visibility') from None
        return found

    def unload(self):
        self.validate()
        if self.own_processes():
            raise Refusal('browser_running')
        if self.policy_owned and self.loaded():
            self.parser('--remove')
        if self.loaded():
            raise Refusal('policy_removal')
        self.policy_owned = False
        return {'ok': True}

    def load(self):
        self.validate()
        if self.own_processes() or self.loaded():
            raise Refusal('collision')
        self.policy_owned = True  # Cleanup even if the parser times out after loading.
        self.parser('--add')  # Never replace existing policy; never reload a directory/service.
        if not self.loaded():
            raise Refusal('policy_absent')
        return {'ok': True}

    def cleanup(self):
        result = {'ok': True, 'profile_removed': False, 'runtime_removed': False, 'processes_stopped': False}
        if not self.created:
            # No ownership means no deletion, including collisions.
            return {key: True for key in result}
        try:
            # Normal diagnostics already cleaned groups/profiles. On EOF/interruption,
            # fallback targets only exact executables inside our unique protected tree.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                for pid in self.own_processes():
                    try:
                        # Pin identity before rechecking; never signal a recycled PID.
                        descriptor = os.pidfd_open(pid)
                        try:
                            process = Path('/proc') / str(pid)
                            if (process.stat().st_uid == self.uid
                                    and (process / 'exe').readlink().is_relative_to(self.runtime)):
                                signal.pidfd_send_signal(descriptor, sig)
                        finally:
                            os.close(descriptor)
                    except (FileNotFoundError, ProcessLookupError):
                        pass
                deadline = time.monotonic() + 5
                while self.own_processes() and time.monotonic() < deadline:
                    time.sleep(0.1)
            result['processes_stopped'] = not self.own_processes()
            if not result['processes_stopped']:
                return result
            if self.policy_owned and self.loaded():
                self.parser('--remove')
            result['profile_removed'] = not self.loaded()
            if not result['profile_removed']:
                return result
            # Only the directory this process exclusively created; no broad rm/chown.
            protected_ancestors(self.base)
            shutil.rmtree(self.base)
            result['runtime_removed'] = not self.base.exists()
            self.created = False
        except (ValueError, OSError, subprocess.SubprocessError):
            pass
        return result


def main():
    # Sudo authorization is solely in the reviewed manual-main workflow. This helper
    # accepts no base path, parser, policy name, profile text or executable override.
    if (platform.system() != 'Linux' or os.geteuid() != 0 or len(sys.argv) != 4
            or not sys.argv[2].isdigit() or not sys.argv[3].isdigit()
            or int(sys.argv[2]) == 0 or os.environ.get('SUDO_UID') != sys.argv[2]
            or os.environ.get('SUDO_GID') != sys.argv[3]):
        return 1
    owner = Owner(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
    cleaning = False
    def interrupt(_signum, _frame):
        if not cleaning:
            raise KeyboardInterrupt
    for signum in HANDLED_SIGNALS:
        signal.signal(signum, interrupt)
    action = 'protocol'
    failure = None
    try:
        while True:
            line = sys.stdin.readline(130)
            if not line:
                break
            action = 'protocol'
            if len(line) > 128:
                raise Refusal('invalid_request')
            try:
                command = json.loads(line, object_pairs_hook=unique_object)
            except ValueError:
                raise Refusal('invalid_request') from None
            if (not isinstance(command, dict) or set(command) != {'action'}
                    or not isinstance(command['action'], str)
                    or command['action'] not in {'stage', 'load', 'unload', 'cleanup'}):
                raise Refusal('invalid_request')
            action = command['action']
            if action == 'cleanup':
                break
            if action == 'stage' and owner.created:
                raise Refusal('invalid_request')
            signal.alarm(150)
            response = getattr(owner, action)()
            signal.alarm(0)
            print(json.dumps(response), flush=True)
    except (Exception, KeyboardInterrupt) as error:
        # Never stringify unknown errors (including syscall/parser exceptions).
        reason = ('interrupted' if isinstance(error, KeyboardInterrupt) else
                  error.args[0] if type(error) is Refusal and len(error.args) == 1
                  and isinstance(error.args[0], str) and error.args[0] in FAILURE_REASONS else 'unexpected_error')
        failure = {'action': action, 'reason': reason}
    finally:
        cleaning = True
        signal.alarm(0)
        result = owner.cleanup()
        if failure is not None:
            result['failure'] = failure
            result['candidate_ancestors'] = candidate_ancestors()
        try:
            print(json.dumps(result), flush=True)
        except BrokenPipeError:
            pass
    return 0 if all(result.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
