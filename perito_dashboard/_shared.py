"""Unprivileged shared policy and serialization helpers."""
import json


CUTOFF = "2025-06"
PF_ORGANIZATION = {
    "code": 20115,
    "name": "DEPARTAMENTO DE POLICIA FEDERAL",
    "abbreviation": "DPF",
}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
