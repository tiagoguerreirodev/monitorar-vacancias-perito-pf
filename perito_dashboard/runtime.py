"""Exact official Linux runtime assets, installed only within the UF candidate.

No package manager, global browser policy change, or fallback to runner Chrome.
The runner label is not a frozen OS image; actual compatibility requires proof.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
import time
from http.client import HTTPException
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

MANIFEST = Path(__file__).resolve().with_name('collector') / 'runtime.json'


def _digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _download(spec, path, deadline):
    count = 0
    with urlopen(spec['url'], timeout=30) as response, path.open('xb') as output:
        while True:
            if time.monotonic() > deadline:
                raise ValueError('Pinned UF runtime download exceeded deadline')
            block = response.read(1024 * 1024)
            if not block:
                break
            count += len(block)
            if count > spec.get('size', 100_000_000):
                raise ValueError('Pinned UF runtime archive exceeded size bound')
            output.write(block)
    if ('size' in spec and count != spec['size']) or _digest(path) != spec['sha256']:
        raise ValueError('Pinned UF runtime archive checksum/length mismatch')


def ensure_runtime(directory):
    """Return exact verified (Node, Chrome) paths; failures belong to UF only."""
    try:
        return _install_and_verify(directory)
    except (subprocess.SubprocessError, tarfile.TarError, BadZipFile, HTTPException,
            KeyError, TypeError) as exc:
        raise ValueError(f'Pinned UF runtime setup failed ({type(exc).__name__})') from exc


def _install_and_verify(directory):
    root = Path(directory).absolute()
    if root.is_symlink() or (root.exists() and (not root.is_dir() or root.stat().st_uid != os.getuid())):
        raise ValueError('Pinned UF runtime requires an owned directory')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('Pinned UF runtime requires Linux x86_64; local host is not qualification')
    pins = json.loads(MANIFEST.read_text())
    if platform.python_version() != pins['python']['version']:
        raise ValueError('Pinned UF runtime requires Python ' + pins['python']['version'])
    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        deadline = time.monotonic() + 300
        with tempfile.TemporaryDirectory(prefix='.perito-runtime-', dir=root.parent) as temporary:
            stage = Path(temporary)
            _download(pins['node'], stage / 'node.tar.xz', deadline)
            _download(pins['chrome'], stage / 'chrome.zip', deadline)
            # Only the exact hash-verified publisher archives reach extraction.
            with tarfile.open(stage / 'node.tar.xz') as archive:
                archive.extractall(stage)
            (stage / ('node-' + pins['node']['version'] + '-linux-x64')).rename(stage / 'node')
            with ZipFile(stage / 'chrome.zip') as archive:
                archive.extractall(stage)
                for member in archive.infolist():
                    mode = member.external_attr >> 16
                    if mode & 0o111:
                        (stage / member.filename).chmod(0o755)
            (stage / 'node.tar.xz').unlink()
            (stage / 'chrome.zip').unlink()
            _verify_runtime(stage, pins)
            stage.rename(root)
            # TemporaryDirectory tolerates its renamed, now absent original path.
    else:
        _verify_runtime(root, pins)
    return str(root / 'node/bin/node'), str(root / 'chrome-linux64/chrome')


def _verify_runtime(root, pins):
    for executable, key in ((root / 'node/bin/node', 'node'), (root / 'chrome-linux64/chrome', 'chrome')):
        if executable.is_symlink() or _digest(executable) != pins[key]['executable_sha256']:
            raise ValueError('Pinned UF runtime executable checksum mismatch')
        result = subprocess.run([str(executable), '--version'], check=True,
                                capture_output=True, text=True, timeout=10)
        if pins[key]['version'] not in result.stdout.split():
            raise ValueError('Pinned UF runtime executable version mismatch')
