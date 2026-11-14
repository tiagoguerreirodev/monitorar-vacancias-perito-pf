from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tests.sources import (
    ARCHIVE_URL, CHECK_TIME, ControlledArchive, SEPTEMBER, SEPTEMBER_URL, TABLE, UnavailableUF,
    pf_classes, set_cell, variant,
)


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.site = self.root / "site"

    def refresh(self, source=None, clock=lambda: CHECK_TIME):
        from perito_dashboard import refresh_and_build
        return refresh_and_build(self.data, self.site, source=source or ControlledArchive(), uf_source=UnavailableUF(), clock=clock)

    def test_official_september_reaches_saved_history_and_dashboard(self):
        self.refresh()
        history = json.loads((self.data / "history.json").read_text())
        self.assertEqual(history["schema_version"], 1)
        self.assertEqual(len(history["observations"]), 1)
        snapshot = history["observations"][0]
        self.assertEqual(
            {key: snapshot[key] for key in ("reference_month", "authorized", "distributed", "occupied", "vacant")},
            {"reference_month": "2026-09", "authorized": 1195, "distributed": 1195, "occupied": 1108, "vacant": 87},
        )
        self.assertEqual(snapshot["organization"], {
            "code": 20115, "name": "DEPARTAMENTO DE POLICIA FEDERAL", "abbreviation": "DPF",
        })
        self.assertEqual(snapshot["class_codes"], [901004, 901005, 901006, 901011])
        self.assertEqual(snapshot["source"], {
            "url": SEPTEMBER_URL, "sha256": hashlib.sha256(SEPTEMBER).hexdigest(),
            "retrieved_at": "2026-11-13T12:00:00Z",
        })
        self.assertEqual(json.loads((self.data / "status.json").read_text()), {
            "schema_version": 1, "last_successful_check": "2026-11-13T12:00:00Z",
        })
        self.assertEqual(json.loads((self.site / "data/history.json").read_text()), history)
        html = (self.site / "index.html").read_text()
        for expected in ("Perito Criminal Federal", "Polícia Federal", "1.195", "1.108", "87", SEPTEMBER_URL):
            self.assertIn(expected, html)

    def test_incomplete_or_ambiguous_pf_class_selection_fails_first_import(self):
        def missing(table, header):
            table.remove(pf_classes(table, header)[-1])

        def duplicate(table, header):
            table.append(deepcopy(pf_classes(table, header)[0]))

        def unknown(table, header):
            row = deepcopy(pf_classes(table, header)[0])
            set_cell(row, header, "CARGO", "901099")
            table.append(row)

        def wrong_name(table, header):
            set_cell(pf_classes(table, header)[0], header, "NOME_CARGO", "DELEGADO DE POLICIA FEDERAL")

        def wrong_org(table, header):
            set_cell(pf_classes(table, header)[0], header, "NOME_ORGAO", "OUTRO ORGAO")

        for edit in (missing, duplicate, unknown, wrong_name, wrong_org):
            with self.subTest(source=edit.__name__):
                content = variant(edit)
                with self.assertRaisesRegex(ValueError, "PF|PCF|class|organization"):
                    self.refresh(ControlledArchive({SEPTEMBER_URL: content}))
                self.assertFalse((self.data / "history.json").exists())
                self.assertFalse((self.site / "index.html").exists())

    def test_invalid_period_counts_or_required_fields_do_not_publish(self):
        scenarios = (
            ("ANO_MES", "202610"), ("ANO_MES", "202613"),
            ("APROVADA", "835.5"), ("OCUPADA", "-1"),
            ("VAGA", "25"), ("VAGA", ""),
        )
        for name, value in scenarios:
            with self.subTest(field=name, value=value):
                def edit(table, header):
                    set_cell(pf_classes(table, header)[0], header, name, value)
                content = variant(edit)
                with self.assertRaisesRegex(ValueError, "period|count|reconcil|field"):
                    self.refresh(ControlledArchive({SEPTEMBER_URL: content}))
                self.assertFalse(self.data.exists())
                self.assertFalse(self.site.exists())

        def missing_field(table, header):
            set_cell(table.find(TABLE + "table-row"), header, "VAGA", "VAGAS_NOVAS")
        content = variant(missing_field)
        with self.assertRaisesRegex(ValueError, "field"):
            self.refresh(ControlledArchive({SEPTEMBER_URL: content}))
        self.assertFalse(self.data.exists())
        self.assertFalse(self.site.exists())

    def test_cutoff_is_inclusive_and_empty_eligible_archive_cannot_publish(self):
        may_url = ARCHIVE_URL + "2025/CargosVagosVacancias_202505.ods"
        old_year_url = ARCHIVE_URL + "2024/CargosVagosVacancias_202412.ods"
        earlier = {may_url: b"excluded, not downloaded", old_year_url: b"excluded"}
        with self.assertRaisesRegex(ValueError, "eligible.*2025-06"):
            self.refresh(ControlledArchive(earlier))
        self.assertFalse(self.data.exists())
        self.assertFalse(self.site.exists())
        june_url = ARCHIVE_URL + "2025/CargosVagosVacancias_202506.ods"
        june = Path(__file__).parent.joinpath("fixtures/national/CargosVagosVacancias_202506.ods").read_bytes()
        self.refresh(ControlledArchive({**earlier, june_url: june}))
        history = json.loads((self.data / "history.json").read_text())
        self.assertEqual([row["reference_month"] for row in history["observations"]], ["2025-06"])
        row = history["observations"][0]
        self.assertEqual((row["authorized"], row["distributed"], row["occupied"], row["vacant"]),
                         (1195, 1195, 1116, 79))
        self.assertEqual(row["source"]["url"], june_url)
        self.assertEqual(json.loads((self.site / "data/history.json").read_text()), history)
        html = (self.site / "index.html").read_text()
        for expected in ("junho de 2025", "1.116", "79", june_url):
            self.assertIn(expected, html)

    def test_lowercase_official_filename_retains_original_url_across_rechecks(self):
        url = ARCHIVE_URL + "2025/cargosvagosvacancias_202508.ods"
        content = Path(__file__).parent.joinpath("fixtures/national/cargosvagosvacancias_202508.ods").read_bytes()
        source = ControlledArchive({url: content})
        self.refresh(source)
        history = json.loads((self.data / "history.json").read_text())
        row = history["observations"][0]
        self.assertEqual((row["reference_month"], row["occupied"], row["vacant"]),
                         ("2025-08", 1111, 84))
        self.assertEqual(row["source"], {
            "url": url, "sha256": hashlib.sha256(content).hexdigest(),
            "retrieved_at": "2026-11-13T12:00:00Z",
        })
        before = (self.data / "history.json").read_bytes()
        self.refresh(source, clock=lambda: CHECK_TIME + timedelta(days=1))
        self.assertEqual((self.data / "history.json").read_bytes(), before)
        self.assertEqual(json.loads((self.site / "data/history.json").read_text()), history)
        self.assertIn(url, (self.site / "index.html").read_text())
        self.assertEqual(json.loads((self.data / "status.json").read_text())[
            "last_successful_check"], "2026-11-14T12:00:00Z")

    def test_failed_build_keeps_previous_accepted_data_and_site(self):
        self.refresh()
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        blocked_site = self.root / "not-a-directory"
        blocked_site.write_text("do not replace")
        with self.assertRaises((OSError, ValueError)):
            from perito_dashboard import refresh_and_build
            refresh_and_build(self.data, blocked_site, source=ControlledArchive(), uf_source=UnavailableUF(),
                              clock=lambda: CHECK_TIME + timedelta(days=1))
        for path, content in before.items():
            self.assertEqual((self.root / path).read_bytes(), content)
        self.assertEqual(blocked_site.read_text(), "do not replace")


if __name__ == "__main__":
    unittest.main()
