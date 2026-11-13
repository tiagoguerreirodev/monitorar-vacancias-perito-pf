"""Internal source discovery, ODS aggregation and persistence."""
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html.parser import HTMLParser
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.request import urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from ._render import render_site

ARCHIVE_URL = "https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/"
CUTOFF = "2026-09"
CLASSES = {
    901004: "PERITO CRIMINAL FEDERAL CLASSE ESPECIAL",
    901005: "PERITO CRIMINAL FEDERAL 1A CLASSE",
    901006: "PERITO CRIMINAL FEDERAL 2A CLASSE",
    901011: "PERITO CRIMINAL FEDERAL 3A CLASSE",
}
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"


class _OfficialArchive:
    def _get(self, url):
        with urlopen(url, timeout=30) as response:
            return response.read()

    def archive_index(self):
        return self._get(ARCHIVE_URL).decode("utf-8")

    def year_index(self, year):
        return self._get(ARCHIVE_URL + year + "/").decode("utf-8")

    def spreadsheet(self, url):
        return self._get(url)


class _Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def _discover(source):
    resources = []
    for year in sorted(set(_Links(source.archive_index()).links)):
        if not re.fullmatch(r"\d{4}/", year) or year[:4] < CUTOFF[:4]:
            continue
        for name in sorted(set(_Links(source.year_index(year[:4])).links)):
            match = re.fullmatch(r"CargosVagosVacancias_(\d{4})(\d{2})\.ods", name)
            if match:
                month = match[1] + "-" + match[2]
                if month >= CUTOFF:
                    resources.append((month, ARCHIVE_URL + year + name))
    return resources


def _cells(row, width=None):
    values = []
    for cell in row:
        if cell.tag not in (TABLE + "table-cell", TABLE + "covered-table-cell"):
            continue
        value = cell.get(OFFICE + "value", "".join(cell.itertext())).strip()
        count = int(cell.get(TABLE + "number-columns-repeated", "1"))
        remaining = (width if width is not None else 16384) - len(values)
        values.extend([value] * min(count, remaining))
        if width is not None and len(values) == width:
            break
    if width is None:
        while values and not values[-1]:
            values.pop()
    return values


def _count(value, field):
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError(f"Invalid count in field {field}: {value!r}") from None
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise ValueError(f"Invalid count in field {field}: {value!r}")
    return int(number)


def _snapshot(content, month, url, checked_at):
    with ZipFile(BytesIO(content)) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    for table in root.iter(TABLE + "table"):
        rows = iter(table.findall(TABLE + "table-row"))
        header = _cells(next(rows))
        if "CARGO" not in header:
            continue
        required = {"ANO_MES", "ORGAO", "NOME_ORGAO", "SIGLA_ORGAO", "CARGO", "NOME_CARGO",
                    "APROVADA", "DISTRIBUIDA", "OCUPADA", "VAGA"}
        if not required.issubset(header) or len(header) != len(set(header)):
            raise ValueError(f"Missing or duplicate required fields: {sorted(required - set(header))}")
        selected = []
        seen = set()
        for row in rows:
            values = _cells(row, len(header))
            if not any(values):
                continue
            item = dict(zip(header, values))
            if not required.issubset(item):
                raise ValueError("Missing required fields in source row")
            if _count(item["ANO_MES"], "reference period") != int(month.replace("-", "")):
                raise ValueError(f"Source reference period does not match resource month {month}")
            if _count(item["ORGAO"], "ORGAO") != 20115:
                continue
            if (item["NOME_ORGAO"] != "DEPARTAMENTO DE POLICIA FEDERAL"
                    or item["SIGLA_ORGAO"] != "DPF"):
                raise ValueError("PF organization identity mismatch")
            code = _count(item["CARGO"], "CARGO")
            if code not in CLASSES:
                if "PERITO CRIMINAL FEDERAL" in item["NOME_CARGO"]:
                    raise ValueError(f"Unexpected PCF class code: {code}")
                continue
            if item["NOME_CARGO"] != CLASSES[code]:
                raise ValueError(f"PCF class code/name mismatch: {code}")
            if code in seen or int(row.get(TABLE + "number-rows-repeated", "1")) != 1:
                raise ValueError(f"Duplicate PCF class: {code}")
            seen.add(code)
            for field in ("APROVADA", "DISTRIBUIDA", "OCUPADA", "VAGA"):
                item[field] = _count(item[field], field)
            selected.append(item)
        if seen != set(CLASSES):
            raise ValueError(f"Missing PCF classes: {sorted(set(CLASSES) - seen)}")
        if sum(row["APROVADA"] for row in selected) != sum(row["OCUPADA"] + row["VAGA"] for row in selected):
            raise ValueError("PCF totals do not reconcile: APROVADA != OCUPADA + VAGA")
        return {
            "reference_month": month,
            "authorized": sum(row["APROVADA"] for row in selected),
            "distributed": sum(row["DISTRIBUIDA"] for row in selected),
            "occupied": sum(row["OCUPADA"] for row in selected),
            "vacant": sum(row["VAGA"] for row in selected),
            "organization": {"code": 20115, "name": "DEPARTAMENTO DE POLICIA FEDERAL", "abbreviation": "DPF"},
            "class_codes": sorted(CLASSES),
            "source": {"url": url, "sha256": hashlib.sha256(content).hexdigest(), "retrieved_at": checked_at},
        }
    raise ValueError("Missing per-organization/per-cargo table")


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _promote(staged):
    """Promote complete candidate directories; roll back ordinary I/O failures."""
    backups, installed = [], []
    try:
        for candidate, target in staged:
            backup = candidate.parent / "previous"
            if target.exists():
                os.replace(target, backup)
                backups.append((backup, target))
            os.replace(candidate, target)
            installed.append(target)
    except OSError:
        for target in reversed(installed):
            shutil.rmtree(target)
        for backup, target in reversed(backups):
            os.replace(backup, target)
        raise


def refresh_and_build(data_dir, site_dir, *, source=None, clock=None):
    """Reconcile official responses, save aggregate history, build a static site.

    source and clock substitute external boundaries for deterministic acceptance
    tests. Production callers normally supply only the two output directories.
    """
    source = source if source is not None else _OfficialArchive()
    now = clock() if clock is not None else datetime.now(timezone.utc)
    checked_at = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    data_dir, site_dir = Path(data_dir), Path(site_dir)
    observations = [_snapshot(source.spreadsheet(url), month, url, checked_at)
                    for month, url in _discover(source)]
    if not observations:
        raise ValueError(f"No eligible official observations at or after {CUTOFF}; nothing published")
    history = {"schema_version": 1, "observations": observations}
    status = {"schema_version": 1, "last_successful_check": checked_at}
    data_path, site_path = data_dir.resolve(), site_dir.resolve()
    if data_path == site_path or data_path in site_path.parents or site_path in data_path.parents:
        raise ValueError("Data and site directories must be separate, non-nested directories")
    for target in (data_dir, site_dir):
        if target.exists() and not target.is_dir():
            raise ValueError(f"Output path is not a directory: {target}")
    with ExitStack() as stack:
        staged = []
        for target in (data_dir, site_dir):
            target.parent.mkdir(parents=True, exist_ok=True)
            work = Path(stack.enter_context(tempfile.TemporaryDirectory(
                prefix=f".{target.name}-", dir=target.parent,
            )))
            candidate = work / "candidate"
            candidate.mkdir()
            staged.append((candidate, target))
        _json(staged[0][0] / "history.json", history)
        _json(staged[0][0] / "status.json", status)
        render_site(history, status, staged[1][0])
        _promote(staged)
