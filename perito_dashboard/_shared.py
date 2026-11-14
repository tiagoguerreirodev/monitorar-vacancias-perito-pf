"""Unprivileged shared policy, serialization and file-byte identity helpers."""
import hashlib
import json
from pathlib import Path


CUTOFF = "2025-06"
PF_ORGANIZATION = {
    "code": 20115,
    "name": "DEPARTAMENTO DE POLICIA FEDERAL",
    "abbreviation": "DPF",
}


def file_digest(path):
    """Return the SHA256 of a file without loading the whole file into memory."""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
