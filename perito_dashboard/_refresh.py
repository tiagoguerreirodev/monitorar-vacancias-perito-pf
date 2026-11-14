"""Internal source discovery, ODS aggregation and persistence."""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
from html.parser import HTMLParser
from http.client import IncompleteRead
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from ._render import render_site
from ._shared import CUTOFF, PF_ORGANIZATION, write_json

ARCHIVE_URL = "https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/"
CLASSES = {
    901004: "PERITO CRIMINAL FEDERAL CLASSE ESPECIAL",
    901005: "PERITO CRIMINAL FEDERAL 1A CLASSE",
    901006: "PERITO CRIMINAL FEDERAL 2A CLASSE",
    901011: "PERITO CRIMINAL FEDERAL 3A CLASSE",
}
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


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


def _request(fetch, url):
    """Bound each download to three attempts; validation failures are not retried."""
    for attempt in range(1, 4):
        try:
            return fetch()
        except (HTTPError, URLError, TimeoutError, ConnectionError, IncompleteRead) as exc:
            transient = not isinstance(exc, HTTPError) or exc.code == 429 or 500 <= exc.code < 600
            if not transient or attempt == 3:
                raise ValueError(f"Source request failed for {url} after {attempt} attempt(s): {exc}") from exc
            time.sleep(0.1 * attempt)
        except UnicodeError as exc:
            raise ValueError(f"Invalid source index encoding for {url}: {exc}") from exc


class _DirectoryIndex(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.heading = ""
        self.links = []
        self.has_parent = False
        self.in_heading = self.in_listing = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "h1":
            self.in_heading = True
        elif tag == "pre":
            self.in_listing = True
        elif tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)
            if self.in_listing and ("href", "../") in attrs:
                self.has_parent = True

    def handle_endtag(self, tag):
        if tag == "h1":
            self.in_heading = False
        elif tag == "pre":
            self.in_listing = False

    def handle_data(self, data):
        if self.in_heading:
            self.heading += data


def _index(fetch, url):
    listing = _DirectoryIndex(_request(fetch, url))
    expected_heading = "Index of " + unquote(urlsplit(url).path)
    # Official nginx indexes identify their path and include a parent entry in
    # a preformatted listing, even when a newly created year has no resources.
    if listing.heading.strip() != expected_heading or not listing.has_parent:
        raise ValueError(f"Unexpected source index format: {url}")
    return sorted(set(listing.links))


def _canonical_basename(month):
    return "cargosvagosvacancias_" + month.replace("-", "") + ".ods"


def _discover(source):
    resources = []
    for year in _index(source.archive_index, ARCHIVE_URL):
        if not re.fullmatch(r"\d{4}/", year) or year[:4] < CUTOFF[:4]:
            continue
        listing = _index(lambda: source.year_index(year[:4]), ARCHIVE_URL + year)
        for name in listing:
            match = re.fullmatch(r"CargosVagosVacancias_(\d{4})(\d{2})([^/]*)", name,
                                 flags=re.IGNORECASE)
            if match:
                month = match[1] + "-" + match[2]
                if not 1 <= int(match[2]) <= 12:
                    raise ValueError(f"Invalid resource month: {name}")
                if month < CUTOFF:
                    continue
                if match[1] != year[:4]:
                    raise ValueError(f"Resource month/year directory mismatch: {year}{name}")
                if name.lower() != _canonical_basename(month):
                    raise ValueError(f"Conflicting noncanonical resource for {month}; maintainer review required: {name}")
                resources.append((month, ARCHIVE_URL + year + name))
            elif name.lower().startswith("cargosvagosvacancias_"):
                raise ValueError(f"Invalid source resource name: {year}{name}")
    return resources


def _repeat(element, attribute, namespace=TABLE):
    value = element.get(namespace + attribute, "1")
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise ValueError(f"Invalid ODS repetition {attribute}: {value!r}")
    return int(value)


def _cell_text(element):
    values = [element.text or ""]
    for child in element:
        if child.tag == TEXT + "s":
            values.append(" " * _repeat(child, "c", TEXT))
        elif child.tag == TEXT + "tab":
            values.append("\t")
        elif child.tag == TEXT + "line-break":
            values.append("\n")
        else:
            values.append(_cell_text(child))
        if child.tag == TEXT + "p":
            values.append("\n")
        values.append(child.tail or "")
    return "".join(values)


def _cells(row, width=None):
    values = []
    for cell in row:
        if cell.tag not in (TABLE + "table-cell", TABLE + "covered-table-cell"):
            continue
        if cell.get(OFFICE + "value-type") == "boolean":
            value = cell.get(OFFICE + "boolean-value", "boolean")
        else:
            value = cell.get(OFFICE + "value", cell.get(OFFICE + "string-value", _cell_text(cell))).strip()
        count = _repeat(cell, "number-columns-repeated")
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
    snapshot = None
    for table in root.iter(TABLE + "table"):
        rows = iter(table.iter(TABLE + "table-row"))
        first_row = next(rows, None)
        if first_row is None:
            continue
        header = _cells(first_row)
        if "CARGO" not in header:
            continue
        if snapshot is not None:
            raise ValueError("Competing per-organization/per-cargo tables")
        if _repeat(first_row, "number-rows-repeated") != 1:
            raise ValueError("Duplicate per-cargo header rows")
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
            if _count(item["ORGAO"], "ORGAO") != PF_ORGANIZATION["code"]:
                continue
            if (item["NOME_ORGAO"] != PF_ORGANIZATION["name"]
                    or item["SIGLA_ORGAO"] != PF_ORGANIZATION["abbreviation"]):
                raise ValueError("PF organization identity mismatch")
            code = _count(item["CARGO"], "CARGO")
            if code not in CLASSES:
                if "PERITO CRIMINAL FEDERAL" in " ".join(item["NOME_CARGO"].upper().split()):
                    raise ValueError(f"Unexpected PCF class code: {code}")
                continue
            if item["NOME_CARGO"] != CLASSES[code]:
                raise ValueError(f"PCF class code/name mismatch: {code}")
            if code in seen or _repeat(row, "number-rows-repeated") != 1:
                raise ValueError(f"Duplicate PCF class: {code}")
            seen.add(code)
            for field in ("APROVADA", "DISTRIBUIDA", "OCUPADA", "VAGA"):
                item[field] = _count(item[field], field)
            if item["APROVADA"] != item["OCUPADA"] + item["VAGA"]:
                raise ValueError(f"PCF class {code} counts do not reconcile: APROVADA != OCUPADA + VAGA")
            selected.append(item)
        if seen != set(CLASSES):
            raise ValueError(f"Missing PCF classes: {sorted(set(CLASSES) - seen)}")
        if sum(row["APROVADA"] for row in selected) != sum(row["OCUPADA"] + row["VAGA"] for row in selected):
            raise ValueError("PCF totals do not reconcile: APROVADA != OCUPADA + VAGA")
        snapshot = {
            "reference_month": month,
            "authorized": sum(row["APROVADA"] for row in selected),
            "distributed": sum(row["DISTRIBUIDA"] for row in selected),
            "occupied": sum(row["OCUPADA"] for row in selected),
            "vacant": sum(row["VAGA"] for row in selected),
            "organization": PF_ORGANIZATION.copy(),
            "class_codes": sorted(CLASSES),
            "source": {"url": url, "sha256": hashlib.sha256(content).hexdigest(), "retrieved_at": checked_at},
        }
    if snapshot is None:
        raise ValueError("Missing per-organization/per-cargo table")
    return snapshot


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


@contextmanager
def _output_lock(target):
    # Stable lock in OS temp storage: deleting an unlocked lock file can let two
    # processes lock different inodes for the same output. Never unlink it.
    directory = Path(tempfile.gettempdir()) / f"perito-dashboard-{os.getuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    name = hashlib.sha256(os.fsencode(target)).hexdigest() + ".lock"
    with (directory / name).open("a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f"Concurrent refresh: output is locked: {target}") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def refresh_and_build(data_dir, site_dir, *, source=None, clock=None):
    """Reconcile official responses, save aggregate history, build a static site.

    source and clock substitute external boundaries for deterministic acceptance
    tests. Production callers normally supply only the two output directories.
    POSIX advisory locks refuse overlapping writers sharing either output path.
    """
    data_dir, site_dir = Path(data_dir).resolve(), Path(site_dir).resolve()
    if data_dir == site_dir or data_dir in site_dir.parents or site_dir in data_dir.parents:
        raise ValueError("Data and site directories must be separate, non-nested directories")
    for target in (data_dir, site_dir):
        if target.exists() and not target.is_dir():
            raise ValueError(f"Output path is not a directory: {target}")
    with ExitStack() as stack:
        for target in sorted((data_dir, site_dir)):
            stack.enter_context(_output_lock(target))
        _refresh_locked(data_dir, site_dir, source if source is not None else _OfficialArchive(), clock)


def _output_state(target):
    """Content signature to detect edits by writers not honoring our locks."""
    if not target.exists():
        return None
    result = []
    for path in [target] + sorted(target.rglob("*")):
        relative = str(path.relative_to(target))
        if path.is_symlink():
            result.append((relative, "symlink", os.readlink(path)))
        elif path.is_file():
            result.append((relative, "file", hashlib.sha256(path.read_bytes()).hexdigest()))
        else:
            result.append((relative, "directory"))
    return result


def _timestamp(value):
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.utcoffset() is not None:
            return instant
    except (AttributeError, TypeError, ValueError):
        pass
    raise ValueError(f"Invalid saved timezone-aware timestamp: {value!r}")


def _validate_source(source, month, successful_check):
    directory = ARCHIVE_URL + month[:4] + "/"
    if (not isinstance(source, dict) or not isinstance(source["url"], str)
            or not source["url"].startswith(directory)
            or source["url"][len(directory):].lower() != _canonical_basename(month)):
        raise ValueError(f"Invalid saved source URL for {month}")
    if not isinstance(source["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
        raise ValueError(f"Invalid saved source fingerprint for {month}")
    if _timestamp(source["retrieved_at"]) > successful_check:
        raise ValueError(f"Saved retrieval time is later than successful check for {month}")


def _validate_observation(row, successful_check):
    if not isinstance(row, dict):
        raise ValueError("Invalid saved observation")
    month = row["reference_month"]
    if (not isinstance(month, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month)
            or month < CUTOFF):
        raise ValueError(f"Invalid saved reference month: {month!r}")
    for field in ("authorized", "distributed", "occupied", "vacant"):
        if type(row[field]) is not int or row[field] < 0:
            raise ValueError(f"Invalid saved aggregate count: {field}")
    if row["authorized"] != row["occupied"] + row["vacant"]:
        raise ValueError("Saved aggregate counts do not reconcile")
    if row["organization"] != PF_ORGANIZATION:
        raise ValueError("Invalid saved PF organization identity")
    if row["class_codes"] != sorted(CLASSES):
        raise ValueError("Invalid saved PCF class identifiers")
    _validate_source(row["source"], month, successful_check)


def _saved_history(data_dir):
    history_file, status_file = data_dir / "history.json", data_dir / "status.json"
    if not history_file.exists() and not status_file.exists():
        return {"schema_version": 1, "observations": []}, None
    try:
        if not history_file.exists() or not status_file.exists():
            raise ValueError("Both saved history.json and status.json are required")
        history = json.loads(history_file.read_text(encoding="utf-8"))
        status = json.loads(status_file.read_text(encoding="utf-8"))
        for document in (history, status):
            if (not isinstance(document, dict) or type(document["schema_version"]) is not int
                    or document["schema_version"] != 1):
                raise ValueError("Unsupported saved schema_version")
        successful_check = _timestamp(status["last_successful_check"])
        if not isinstance(history["observations"], list):
            raise ValueError("Saved observations must be a list")
        months = set()
        for row in history["observations"]:
            _validate_observation(row, successful_check)
            if row["reference_month"] in months:
                raise ValueError(f"Duplicate saved reference month: {row['reference_month']}")
            months.add(row["reference_month"])
        if not isinstance(history.get("corrections", []), list):
            raise ValueError("Saved corrections must be a list")
        for correction in history.get("corrections", []):
            if not isinstance(correction, dict):
                raise ValueError("Invalid saved correction audit")
            _validate_observation(correction["superseded"], successful_check)
            _validate_source(correction["replacement_source"],
                             correction["superseded"]["reference_month"], successful_check)
        return history, successful_check
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid saved aggregate data in {data_dir}: {exc}") from exc


def _refresh_locked(data_dir, site_dir, source, clock):
    before = (_output_state(data_dir), _output_state(site_dir))
    now = clock() if clock is not None else datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("Execution clock must provide a timezone-aware datetime")
    checked_at = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    history, successful_check = _saved_history(data_dir)
    if successful_check is not None and now < successful_check:
        raise ValueError("Stale refresh: clock predates the last successful check")
    accepted = {row["reference_month"]: row for row in history["observations"]}
    for month, url in _discover(source):
        content = _request(lambda: source.spreadsheet(url), url)
        try:
            observation = _snapshot(content, month, url, checked_at)
        except (ValueError, BadZipFile, ET.ParseError, KeyError) as exc:
            raise ValueError(f"Invalid spreadsheet {url}: {exc}") from exc
        previous = accepted.get(month)
        if previous is not None and previous["source"]["url"] != url:
            raise ValueError(f"Conflicting resource for {month}; maintainer review required: {url}")
        if previous is None or previous["source"]["sha256"] != observation["source"]["sha256"]:
            if previous is not None:
                history.setdefault("corrections", []).append({
                    "superseded": previous, "replacement_source": observation["source"],
                })
            accepted[month] = observation
    observations = [accepted[month] for month in sorted(accepted)]
    if not observations:
        raise ValueError(f"No eligible official observations at or after {CUTOFF}; nothing published")
    history["observations"] = observations
    status = {"schema_version": 1, "last_successful_check": checked_at}
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
        write_json(staged[0][0] / "history.json", history)
        write_json(staged[0][0] / "status.json", status)
        render_site(history, status, staged[1][0])
        if before != (_output_state(data_dir), _output_state(site_dir)):
            raise ValueError("Stale refresh: accepted outputs changed during refresh; nothing promoted")
        _promote(staged)
