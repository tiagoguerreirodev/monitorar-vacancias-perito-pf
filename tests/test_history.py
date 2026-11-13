"""Acceptance coverage through complete refresh/build and persisted artifacts."""
from copy import deepcopy
from datetime import timedelta
import hashlib
from http.client import IncompleteRead
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError, URLError
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from perito_dashboard import refresh_and_build
from tests.sources import (
    ARCHIVE_URL, CHECK_TIME, ControlledArchive, OFFICE, SEPTEMBER_URL, ScriptedArchive, TABLE,
    TEXT, monthly_resource, pf_classes, set_cell, variant,
)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.site = self.root / "site"

    def refresh(self, source=None, instant=CHECK_TIME):
        refresh_and_build(self.data, self.site,
                          source=source if source is not None else ControlledArchive(),
                          clock=lambda: instant)

    def history(self):
        saved = json.loads((self.data / "history.json").read_text())
        self.assertEqual(json.loads((self.site / "data/history.json").read_text()), saved)
        self.assertEqual((self.site / "data/status.json").read_bytes(),
                         (self.data / "status.json").read_bytes())
        self.assertIn("Perito Criminal Federal", (self.site / "index.html").read_text())
        return saved

    def output_bytes(self):
        return {path.relative_to(self.root): path.read_bytes()
                for directory in (self.data, self.site) for path in directory.rglob("*")
                if path.is_file()}

    def test_ambiguous_or_misfiled_resources_do_not_replace_last_good_outputs(self):
        self.refresh()
        before = self.output_bytes()
        november_url, november = monthly_resource("2026-11")
        invalid_url, invalid = monthly_resource("2026-13")
        scenarios = [
            {november_url: november, november_url.replace(".ods", "_v2.ods"): november},
            {november_url.replace("/2026/", "/2027/"): november},
            {invalid_url: invalid},
        ]
        for resources in scenarios:
            with self.subTest(resources=list(resources)):
                with self.assertRaisesRegex(ValueError, "[Cc]onflict|month|year"):
                    self.refresh(ControlledArchive(resources), CHECK_TIME + timedelta(days=1))
                self.assertEqual(self.output_bytes(), before)

    def test_normal_ods_attributes_reordering_repeats_and_grouped_rows_are_accepted(self):
        def representations(table, header):
            selected = pf_classes(table, header)
            rows = table.findall(TABLE + "table-row")
            for row in rows:
                cells = list(row)
                for cell in cells[:len(header)]:
                    text = "".join(cell.itertext())
                    if cell.get(OFFICE + "value-type") == "string":
                        cell.set(OFFICE + "string-value", text)
                    elif cell.get(OFFICE + "value") is not None:
                        cell.set(OFFICE + "value", cell.get(OFFICE + "value") + ".0")
                    cell[:] = []
                row[:] = list(reversed(cells[:len(header)])) + cells[len(header):]
                if row in selected:
                    # APROVADA and DISTRIBUIDA are equal in this official fixture.
                    repeated = row[len(header) - 1 - header.index("DISTRIBUIDA")]
                    repeated.set(TABLE + "number-columns-repeated", "2")
                    row.remove(row[len(header) - 1 - header.index("APROVADA")])
                table.remove(row)
            ET.SubElement(table, TABLE + "table-header-rows").append(rows[0])
            ET.SubElement(table, TABLE + "table-rows").extend(rows[1:])
        content = variant(representations)
        self.refresh(ControlledArchive({SEPTEMBER_URL: content}))
        row = self.history()["observations"][0]
        self.assertEqual((row["authorized"], row["distributed"], row["occupied"], row["vacant"]),
                         (1195, 1195, 1108, 87))

    def test_ods_text_spaces_are_strings_and_boolean_cells_are_not_numeric_counts(self):
        def spaced_names(table, header):
            for row in pf_classes(table, header):
                for field in ("NOME_ORGAO", "NOME_CARGO"):
                    cell = row[header.index(field)]
                    words = "".join(cell.itertext()).split(" ")
                    cell[:] = []
                    paragraph = ET.SubElement(cell, TEXT + "p")
                    paragraph.text = words[0]
                    for word in words[1:]:
                        ET.SubElement(paragraph, TEXT + "s").tail = word
        self.refresh(ControlledArchive({SEPTEMBER_URL: variant(spaced_names)}))
        self.assertEqual(self.history()["observations"][0]["vacant"], 87)
        before = self.output_bytes()

        def boolean_count(table, header):
            row = pf_classes(table, header)[0]
            set_cell(row, header, "DISTRIBUIDA", "0")
            cell = row[header.index("DISTRIBUIDA")]
            cell.set(OFFICE + "value-type", "boolean")
            cell.set(OFFICE + "boolean-value", "false")
        with self.assertRaisesRegex(ValueError, "count|boolean"):
            self.refresh(ControlledArchive({SEPTEMBER_URL: variant(boolean_count)}),
                         CHECK_TIME + timedelta(days=1))
        self.assertEqual(self.output_bytes(), before)

    def test_malformed_sources_and_invalid_counts_preserve_last_good_artifacts(self):
        self.refresh()
        before = self.output_bytes()
        broken_xml = BytesIO()
        with ZipFile(broken_xml, "w") as archive:
            archive.writestr("content.xml", "<broken>")
        missing_xml = BytesIO()
        with ZipFile(missing_xml, "w") as archive:
            archive.writestr("unrelated.xml", "<document/>")

        def unbalanced_classes(table, header):
            first, second = pf_classes(table, header)[:2]
            set_cell(first, header, "VAGA", "25")
            set_cell(second, header, "OCUPADA", "95")

        def unknown_class(table, header):
            row = deepcopy(pf_classes(table, header)[0])
            set_cell(row, header, "CARGO", "901099")
            set_cell(row, header, "NOME_CARGO", "Perito Criminal Federal 4A Classe")
            table.append(row)

        def repeated_header(table, header):
            table.find(TABLE + "table-row").set(TABLE + "number-rows-repeated", "2")

        def invalid_repeat(table, header):
            pf_classes(table, header)[0][0].set(TABLE + "number-columns-repeated", "0")

        cases = [b"not an ODS", broken_xml.getvalue(), missing_xml.getvalue(),
                 variant(unbalanced_classes), variant(unknown_class), variant(repeated_header),
                 variant(invalid_repeat)]
        for value in ("NaN", "Infinity", "-Infinity", "-1", "0.5", "true", ""):
            def invalid_count(table, header):
                set_cell(pf_classes(table, header)[0], header, "APROVADA", value)
            cases.append(variant(invalid_count))
        for content in cases:
            with self.subTest(document=hashlib.sha256(content).hexdigest()):
                with self.assertRaisesRegex(ValueError, SEPTEMBER_URL):
                    self.refresh(ControlledArchive({SEPTEMBER_URL: content}),
                                 CHECK_TIME + timedelta(days=1))
                self.assertEqual(self.output_bytes(), before)

    def test_competing_per_cargo_tables_in_one_resource_fail_without_promotion(self):
        self.refresh()
        before = self.output_bytes()
        with ZipFile(BytesIO(ControlledArchive().spreadsheet(SEPTEMBER_URL))) as archive:
            root = ET.fromstring(archive.read("content.xml"))
        spreadsheet = next(root.iter(OFFICE + "spreadsheet"))
        table = next(table for table in spreadsheet.iter(TABLE + "table")
                     if table.get(TABLE + "name") == "por_Órgao_e_Cargo")
        spreadsheet.append(deepcopy(table))
        output = BytesIO()
        with ZipFile(output, "w") as archive:
            archive.writestr("content.xml", ET.tostring(root, encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "table|[Dd]uplicate|[Cc]ompeting"):
            self.refresh(ControlledArchive({SEPTEMBER_URL: output.getvalue()}),
                         CHECK_TIME + timedelta(days=1))
        self.assertEqual(self.output_bytes(), before)

    def test_archive_and_year_index_format_drift_does_not_count_as_a_successful_check(self):
        self.refresh()
        before = self.output_bytes()
        cases = [
            ("archive", "<html><h1>Service unavailable</h1></html>"),
            ("2026", "unparseable directory response"),
            ("2026", '<a href="CargosVagosVacancias_202610.csv">CSV</a>'),
        ]
        for key, response in cases:
            with self.subTest(boundary=key, response=response):
                with self.assertRaisesRegex(ValueError, "[Ii]ndex|format|resource"):
                    self.refresh(ScriptedArchive({key: [response]}), CHECK_TIME + timedelta(days=1))
                self.assertEqual(self.output_bytes(), before)

    def test_zero_counts_are_observations_and_distributed_is_not_authorized(self):
        def supporting_metadata(table, header):
            for row in pf_classes(table, header):
                set_cell(row, header, "DISTRIBUIDA", "0")
        self.refresh(ControlledArchive({SEPTEMBER_URL: variant(supporting_metadata)}))
        first = self.history()["observations"][0]
        self.assertEqual((first["authorized"], first["distributed"]), (1195, 0))

        def zero(table, header):
            for row in pf_classes(table, header):
                for field in ("APROVADA", "DISTRIBUIDA", "OCUPADA", "VAGA"):
                    set_cell(row, header, field, "0")
        self.refresh(ControlledArchive(dict([monthly_resource("2026-10", zero)])),
                     CHECK_TIME + timedelta(days=1))
        rows = self.history()["observations"]
        self.assertEqual([row["reference_month"] for row in rows], ["2026-09", "2026-10"])
        self.assertEqual((rows[-1]["authorized"], rows[-1]["occupied"], rows[-1]["vacant"]), (0, 0, 0))
        html = (self.site / "index.html").read_text()
        self.assertIn(">0<", html)
        self.assertNotIn("NaN", html)
        self.assertNotIn("Infinity", html)

    def test_transient_network_failures_recover_through_complete_refresh(self):
        self.refresh()
        before = (self.data / "history.json").read_bytes()
        failures = [TimeoutError("timed out"), URLError("connection reset"),
                    IncompleteRead(b"partial ODS", 200),
                    HTTPError(SEPTEMBER_URL, 503, "unavailable", {}, None),
                    HTTPError(SEPTEMBER_URL, 429, "rate limited", {}, None)]
        for key in ("archive", "2026", SEPTEMBER_URL):
            for failure in failures:
                with self.subTest(boundary=key, failure=repr(failure)):
                    self.refresh(ScriptedArchive({key: [failure, failure]}),
                                 CHECK_TIME + timedelta(days=1))
                    self.assertEqual((self.data / "history.json").read_bytes(), before)
                    self.history()
                    self.assertEqual(json.loads((self.data / "status.json").read_text())[
                        "last_successful_check"], "2026-11-14T12:00:00Z")

    def test_exhausted_retries_permanent_http_and_partial_download_keep_last_good(self):
        self.refresh()
        before = self.output_bytes()
        for key, label in (("archive", ARCHIVE_URL), ("2026", ARCHIVE_URL + "2026/"),
                           (SEPTEMBER_URL, SEPTEMBER_URL)):
            with self.subTest(boundary=key):
                source = ScriptedArchive({key: [TimeoutError("timed out")] * 3})
                with self.assertRaisesRegex(ValueError, "after 3 attempt") as error:
                    self.refresh(source, CHECK_TIME + timedelta(days=1))
                self.assertIn(label, str(error.exception))
                self.assertEqual(self.output_bytes(), before)
        source = ScriptedArchive({SEPTEMBER_URL: [
            HTTPError(SEPTEMBER_URL, 404, "missing", {}, None),
        ]})
        with self.assertRaisesRegex(ValueError, "after 1 attempt.*404"):
            self.refresh(source, CHECK_TIME + timedelta(days=1))
        self.assertEqual(self.output_bytes(), before)
        good_url, good = monthly_resource("2026-10")
        partial_url, partial = monthly_resource("2026-11")
        with self.assertRaisesRegex(ValueError, partial_url):
            self.refresh(ControlledArchive({good_url: good, partial_url: partial[:100]}),
                         CHECK_TIME + timedelta(days=1))
        self.assertEqual(self.output_bytes(), before)

    def test_concurrent_refresh_is_refused_without_overwriting_the_inflight_run(self):
        self.refresh()
        before = self.output_bytes()
        entered, release = threading.Event(), threading.Event()
        errors = []

        class SlowArchive(ControlledArchive):
            def spreadsheet(self, url):
                entered.set()
                if not release.wait(10):
                    raise AssertionError("test did not release controlled source")
                return super().spreadsheet(url)

        def slow_refresh():
            try:
                self.refresh(SlowArchive(), CHECK_TIME + timedelta(days=1))
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=slow_refresh)
        thread.start()
        try:
            self.assertTrue(entered.wait(5), "controlled request was not reached")
            for data, site in ((self.data, self.site), (self.data, self.root / "other-site"),
                               (self.root / "other-data", self.site)):
                with self.subTest(shared_outputs=(data, site)):
                    with self.assertRaisesRegex(ValueError, "[Cc]oncurrent|locked"):
                        refresh_and_build(data, site, source=ControlledArchive(),
                                          clock=lambda: CHECK_TIME + timedelta(days=2))
                    self.assertEqual(self.output_bytes(), before)
                    self.assertFalse((self.root / "other-data").exists())
                    self.assertFalse((self.root / "other-site").exists())
            command = subprocess.run([
                sys.executable, "-m", "perito_dashboard", "--data-dir", str(self.data),
                "--site-dir", str(self.site),
            ], capture_output=True, text=True, timeout=10)
            self.assertEqual(command.returncode, 1)
            self.assertIn("Concurrent refresh", command.stderr)
            self.assertEqual(self.output_bytes(), before)
        finally:
            release.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.history()
        self.assertEqual(json.loads((self.data / "status.json").read_text())[
            "last_successful_check"], "2026-11-14T12:00:00Z")

    def test_stale_outputs_changed_during_collection_are_not_overwritten(self):
        self.refresh()
        for relative in ("data/history.json", "data/status.json", "site/index.html"):
            with self.subTest(external_writer=relative):
                changed = []
                owner = self

                class ConcurrentEditor(ControlledArchive):
                    def spreadsheet(self, url):
                        target = owner.root / relative
                        target.write_bytes(target.read_bytes() + b"\n")
                        changed.append(owner.output_bytes())
                        return super().spreadsheet(url)
                with self.assertRaisesRegex(ValueError, "[Ss]tale|changed during"):
                    self.refresh(ConcurrentEditor(), CHECK_TIME + timedelta(days=1))
                self.assertEqual(self.output_bytes(), changed[0])

    def test_stale_or_timezone_naive_check_cannot_move_success_time_backward(self):
        self.refresh()
        before = self.output_bytes()
        for instant in (CHECK_TIME - timedelta(seconds=1), CHECK_TIME.replace(tzinfo=None)):
            with self.subTest(clock=instant):
                with self.assertRaisesRegex(ValueError, "[Ss]tale|clock|timezone"):
                    self.refresh(instant=instant)
                self.assertEqual(self.output_bytes(), before)

    def test_invalid_saved_history_or_status_fails_closed_instead_of_discarding_records(self):
        self.refresh()
        baseline = self.output_bytes()
        history = json.loads((self.data / "history.json").read_text())
        cases = []
        duplicate = deepcopy(history)
        duplicate["observations"].append(deepcopy(duplicate["observations"][0]))
        cases.append(("history.json", duplicate))
        for key, value in (("reference_month", "2026-08"), ("reference_month", "2026-13"),
                           ("authorized", True), ("occupied", -1), ("vacant", 87.5),
                           ("authorized", 1196), ("class_codes", [901004]),
                           ("organization", {"code": 1})):
            invalid = deepcopy(history)
            invalid["observations"][0][key] = value
            cases.append(("history.json", invalid))
        for key, value in (("url", "https://example.org/untrusted.ods"), ("sha256", "invalid"),
                           ("retrieved_at", "2026-11-13T12:00:00")):
            invalid = deepcopy(history)
            invalid["observations"][0]["source"][key] = value
            cases.append(("history.json", invalid))
        cases.extend([
            ("history.json", {**history, "schema_version": 2}),
            ("history.json", {**history, "observations": None}),
            ("history.json", {**history, "corrections": ["invalid"]}),
            ("status.json", {"schema_version": 2, "last_successful_check": "2026-11-13T12:00:00Z"}),
            ("status.json", None),
        ])
        for filename, value in cases:
            with self.subTest(file=filename, value=value):
                for path, content in baseline.items():
                    (self.root / path).write_bytes(content)
                (self.data / filename).write_text(json.dumps(value))
                before = self.output_bytes()
                with self.assertRaisesRegex(ValueError, "[Ss]aved|history|status"):
                    self.refresh(ControlledArchive({}), CHECK_TIME + timedelta(days=1))
                self.assertEqual(self.output_bytes(), before)
        for missing in ("history.json", "status.json"):
            with self.subTest(missing=missing):
                for path, content in baseline.items():
                    (self.root / path).write_bytes(content)
                (self.data / missing).unlink()
                before = self.output_bytes()
                with self.assertRaisesRegex(ValueError, "[Ss]aved|history|status"):
                    self.refresh(instant=CHECK_TIME + timedelta(days=1))
                self.assertEqual(self.output_bytes(), before)

    def test_unchanged_check_keeps_observations_and_advances_only_check_time(self):
        self.refresh()
        before = (self.data / "history.json").read_bytes()
        self.refresh(instant=CHECK_TIME + timedelta(days=1))
        self.assertEqual((self.data / "history.json").read_bytes(), before)
        self.assertEqual(len(self.history()["observations"]), 1)
        self.assertEqual(json.loads((self.data / "status.json").read_text()), {
            "schema_version": 1, "last_successful_check": "2026-11-14T12:00:00Z",
        })

    def test_retained_history_backfills_chronologically_across_years_without_filling_gaps(self):
        self.refresh(ControlledArchive(dict([monthly_resource("2027-01")])))
        january = self.history()["observations"][0]
        # The latest source disappears while older eligible months are discovered.
        self.refresh(ControlledArchive(dict([
            monthly_resource("2026-11"), monthly_resource("2026-09"),
            (ARCHIVE_URL + "2026/CargosVagosVacancias_202608.ods", b"outside cutoff"),
        ])), CHECK_TIME + timedelta(days=1))
        rows = self.history()["observations"]
        self.assertEqual([row["reference_month"] for row in rows], ["2026-09", "2026-11", "2027-01"])
        self.assertEqual(rows[-1], january)
        self.assertEqual(len({row["reference_month"] for row in rows}), 3)
        self.assertIn(january["source"]["url"], (self.site / "index.html").read_text())
        before = (self.data / "history.json").read_bytes()
        self.refresh(ControlledArchive({}), CHECK_TIME + timedelta(days=2))
        self.assertEqual((self.data / "history.json").read_bytes(), before)
        self.history()

    def test_canonical_correction_keeps_superseded_values_and_provenance_once(self):
        self.refresh()
        previous = self.history()["observations"][0]

        def correction(table, header):
            row = pf_classes(table, header)[0]
            set_cell(row, header, "OCUPADA", "810")
            set_cell(row, header, "VAGA", "25")
        corrected = variant(correction)
        source = ControlledArchive({SEPTEMBER_URL: corrected})
        self.refresh(source, CHECK_TIME + timedelta(days=1))
        history = self.history()
        self.assertEqual(len(history["observations"]), 1)
        current = history["observations"][0]
        self.assertEqual((current["authorized"], current["occupied"], current["vacant"]),
                         (1195, 1107, 88))
        self.assertEqual(current["source"], {
            "url": SEPTEMBER_URL, "sha256": hashlib.sha256(corrected).hexdigest(),
            "retrieved_at": "2026-11-14T12:00:00Z",
        })
        self.assertEqual(history["corrections"], [{
            "superseded": previous, "replacement_source": current["source"],
        }])
        self.refresh(source, CHECK_TIME + timedelta(days=2))
        self.assertEqual(self.history(), history)


if __name__ == "__main__":
    unittest.main()
