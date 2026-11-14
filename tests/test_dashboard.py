"""Dashboard acceptance through the complete refresh/build operation."""
from copy import deepcopy
from datetime import timedelta
from functools import partial
import hashlib
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

from perito_dashboard import refresh_and_build
from tests.sources import (
    CHECK_TIME, ControlledArchive, SEPTEMBER, SEPTEMBER_URL, ScriptedArchive,
    monthly_resource as dated_resource, pf_classes, resource_url, set_cell, variant,
)


def monthly_resource(month, occupied, vacant):
    """A controlled publication using the official sheet structure and identities."""
    def edit(table, header):
        for index, row in enumerate(pf_classes(table, header)):
            for field, count in (("APROVADA", occupied + vacant), ("DISTRIBUIDA", occupied + vacant),
                                 ("OCUPADA", occupied), ("VAGA", vacant)):
                set_cell(row, header, field, count if index == 0 else 0)
    return dated_resource(month, edit)[1]


class Page(HTMLParser):
    """Read semantic output without depending on renderer functions."""
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.stack = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "text": "", "parents": list(self.stack)}
        self.nodes.append(node)
        if tag not in {"meta", "link", "br", "hr", "img", "input"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1]["tag"] == tag:
            self.stack.pop()

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data

    def matching(self, tag=None, **attrs):
        return [node for node in self.nodes
                if (tag is None or node["tag"] == tag)
                and all(node["attrs"].get(key) == value for key, value in attrs.items())]

    def one(self, tag=None, **attrs):
        found = self.matching(tag, **attrs)
        if len(found) != 1:
            raise AssertionError(f"Expected one {tag} {attrs}, found {len(found)}")
        return found[0]

    def text(self, tag=None, **attrs):
        return " ".join(self.one(tag, **attrs)["text"].split())


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.site = self.root / "site"

    def refresh(self, source=None, clock=lambda: CHECK_TIME):
        refresh_and_build(self.data, self.site,
                          source=source if source is not None else ControlledArchive(), clock=clock)
        return Page((self.site / "index.html").read_text(encoding="utf-8"))

    def test_current_pie_explains_official_counts_proportions_and_dates(self):
        page = self.refresh()
        self.assertEqual(page.one("html")["attrs"]["lang"], "pt-BR")
        self.assertEqual(page.text("h1"), "Perito Criminal Federal — Polícia Federal")
        self.assertIn("Totais nacionais", page.text("body"))
        self.assertIn("todas as classes", page.text("body"))
        self.assertEqual(page.text("time", datetime="2026-09"), "setembro de 2026")
        self.assertEqual(page.text("time", datetime="2026-11-13T12:00:00Z"),
                         "13/11/2026 às 09:00 (Brasília, UTC−03:00)")
        self.assertIn("Última verificação bem-sucedida", page.text("body"))
        table = page.text("table", id="current-values")
        for expected in ("Ocupados", "1.108", "92,7%", "Vagos", "87", "7,3%",
                         "Total de cargos aprovados", "1.195"):
            self.assertIn(expected, table)
        pie = page.one("svg", id="current-pie")
        self.assertEqual(pie["attrs"]["role"], "img")
        self.assertIn("current-pie-description", pie["attrs"]["aria-labelledby"])
        self.assertIn("Ocupados: 1.108 (92,7%)", pie["text"])
        self.assertIn("Vagos: 87 (7,3%)", pie["text"])
        # Two nonempty sectors, not a decorative chart unrelated to the data.
        sectors = [node for node in page.matching("path")
                   if pie in node["parents"] and "fill" in node["attrs"]]
        self.assertEqual(len(sectors), 2)
        self.assertNotEqual(sectors[0]["attrs"]["fill"], sectors[1]["attrs"]["fill"])
        self.assertTrue(page.matching("pattern"), "Vacancy pattern provides a non-color cue")
        self.assertIn("não dados em tempo real", page.text("body"))
        self.assertIn("não representam vagas de concurso", page.text("body"))
        self.assertTrue(page.matching("a", href=SEPTEMBER_URL))
        self.assertTrue(page.matching("a", href="https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/gestao-de-pessoas-executivo-federal-cargos-vagos"))
        css = page.one("link", rel="stylesheet")["attrs"]["href"]
        self.assertFalse(css.startswith(("/", "http:", "https:")))
        self.assertTrue((self.site / css).is_file())
        self.assertEqual(json.loads((self.site / "data/history.json").read_text()),
                         json.loads((self.data / "history.json").read_text()))

    def test_one_official_month_is_two_single_points_not_an_invented_trend(self):
        page = self.refresh()
        chart = page.one("svg", id="history-chart")
        self.assertEqual(chart["attrs"]["role"], "img")
        self.assertIn("history-description", chart["attrs"]["aria-labelledby"])
        self.assertIn("Mês de referência oficial", chart["text"])
        self.assertIn("Cargos (quantidade)", chart["text"])
        self.assertIn("set/2026", chart["text"])
        self.assertIn("Ocupados: 1.108 — setembro de 2026", chart["text"])
        self.assertIn("Vagos: 87 — setembro de 2026", chart["text"])
        self.assertEqual(len([n for n in page.matching("circle") if chart in n["parents"]]), 1)
        self.assertEqual(len([n for n in page.matching("rect") if chart in n["parents"]]), 1)
        self.assertFalse([n for n in page.matching("polyline") if chart in n["parents"]])
        self.assertIn("Apenas um mês disponível", page.text("body"))
        self.assertIn("Novos pontos aparecerão", page.text("body"))
        table = page.text("table", id="history-values")
        for expected in ("setembro de 2026", "1.108", "87", "1.195", "Planilha oficial"):
            self.assertIn(expected, table)
        self.assertTrue(all(n["attrs"].get("scope") in ("col", "row")
                            for n in page.matching("th")))

    def test_history_uses_monthly_axis_and_breaks_both_lines_at_missing_months(self):
        source = ControlledArchive({
            resource_url("2027-01"): monthly_resource("2027-01", 1130, 65),
            resource_url("2026-12"): monthly_resource("2026-12", 1120, 75),
            SEPTEMBER_URL: SEPTEMBER,
            resource_url("2026-10"): monthly_resource("2026-10", 1110, 85),
        })
        page = self.refresh(source)
        self.assertEqual(page.text("time", datetime="2027-01"), "janeiro de 2027")
        self.assertIn("1.130", page.text("table", id="current-values"))
        chart = page.one("svg", id="history-chart")
        self.assertIn("novembro de 2026: indisponível", chart["text"])
        table = page.one("table", id="history-values")
        rows = [n for n in page.matching("tr") if table in n["parents"]][1:]
        self.assertEqual(len(rows), 5)
        for row, label in zip(rows, ("setembro de 2026", "outubro de 2026", "novembro de 2026",
                                     "dezembro de 2026", "janeiro de 2027")):
            self.assertIn(label, row["text"])
        self.assertIn("Indisponível", rows[2]["text"])
        self.assertNotIn("0", rows[2]["text"].replace("novembro de 2026", ""))
        circles = [n for n in page.matching("circle") if chart in n["parents"]]
        squares = [n for n in page.matching("rect") if chart in n["parents"]]
        self.assertEqual(len(circles), 4)
        self.assertEqual(len(squares), 4)
        # Equal month spacing, including the missing November slot (not compressed away).
        xs = [float(n["attrs"]["cx"]) for n in circles]
        self.assertAlmostEqual(xs[1] - xs[0], xs[3] - xs[2])
        self.assertAlmostEqual(xs[2] - xs[1], 2 * (xs[1] - xs[0]))
        for series in ("Ocupados", "Vagos"):
            lines = [n for n in page.matching("polyline", **{"aria-label": series})
                     if chart in n["parents"]]
            self.assertEqual(len(lines), 2)
            self.assertTrue(all(len(n["attrs"]["points"].split()) == 2 for n in lines))
            self.assertEqual(bool(lines[0]["attrs"].get("stroke-dasharray")), series == "Vagos")
        for month in ("2026-09", "2026-10", "2026-12", "2027-01"):
            self.assertTrue(page.matching("a", href=resource_url(month)))
        history = json.loads((self.data / "history.json").read_text())
        self.assertEqual(len(history["observations"]), 4)

    def test_reconciled_history_and_dashboard_agree_after_rechecks_correction_and_backfill(self):
        november_url = resource_url("2026-11")
        november = monthly_resource("2026-11", 1120, 75)
        resources = {november_url: november, SEPTEMBER_URL: SEPTEMBER}
        self.refresh(ControlledArchive(resources))
        original = json.loads((self.data / "history.json").read_text())
        original_bytes = (self.data / "history.json").read_bytes()
        september = deepcopy(original["observations"][0])

        # An unchanged check advances operational metadata, not provenance or points.
        page = self.refresh(ControlledArchive(resources),
                            clock=lambda: CHECK_TIME + timedelta(days=1))
        self.assertEqual((self.data / "history.json").read_bytes(), original_bytes)
        self.assertEqual(page.text("time", datetime="2026-11-14T12:00:00Z"),
                         "14/11/2026 às 09:00 (Brasília, UTC−03:00)")
        self.assertEqual(page.text("time", datetime="2026-11"), "novembro de 2026")
        chart = page.one("svg", id="history-chart")
        self.assertEqual(len([n for n in page.matching("circle") if chart in n["parents"]]), 2)
        self.assertEqual(len([n for n in page.matching("rect") if chart in n["parents"]]), 2)
        self.assertIn("outubro de 2026: indisponível", chart["text"])
        self.assertFalse([n for n in page.matching("polyline") if chart in n["parents"]])

        # A canonical correction replaces September once, without moving current back.
        corrected = monthly_resource("2026-09", 1109, 86)
        resources[SEPTEMBER_URL] = corrected
        page = self.refresh(ControlledArchive(resources),
                            clock=lambda: CHECK_TIME + timedelta(days=2))
        history = json.loads((self.data / "history.json").read_text())
        self.assertEqual(len(history["observations"]), 2)
        self.assertEqual(history["corrections"], [{
            "superseded": september,
            "replacement_source": {
                "url": SEPTEMBER_URL, "sha256": hashlib.sha256(corrected).hexdigest(),
                "retrieved_at": "2026-11-15T12:00:00Z",
            },
        }])
        self.assertEqual(page.text("time", datetime="2026-11"), "novembro de 2026")
        self.assertIn("Ocupados: 1.109 — setembro de 2026",
                      page.text("svg", id="history-chart"))
        self.assertIn("Vagos: 86 — setembro de 2026", page.text("svg", id="history-chart"))
        self.assertNotIn("1.108", page.text("table", id="history-values"))

        # Later discovery backfills October, retains missing November and crosses years.
        resources = {
            resource_url("2027-01"): monthly_resource("2027-01", 1130, 65),
            resource_url("2026-10"): monthly_resource("2026-10", 1110, 85),
            SEPTEMBER_URL: corrected,
        }
        page = self.refresh(ControlledArchive(resources),
                            clock=lambda: CHECK_TIME + timedelta(days=3))
        history = json.loads((self.data / "history.json").read_text())
        self.assertEqual([row["reference_month"] for row in history["observations"]],
                         ["2026-09", "2026-10", "2026-11", "2027-01"])
        self.assertEqual(history["observations"][2], original["observations"][1])
        self.assertEqual(len(history["corrections"]), 1, "Unchanged correction is not audited twice")
        self.assertEqual(history["observations"][0]["source"]["retrieved_at"],
                         "2026-11-15T12:00:00Z")
        self.assertEqual(page.text("time", datetime="2027-01"), "janeiro de 2027")
        self.assertEqual(page.text("time", datetime="2026-11-16T12:00:00Z"),
                         "16/11/2026 às 09:00 (Brasília, UTC−03:00)")
        current = page.text("table", id="current-values")
        for value in ("1.130", "65", "1.195", "94,6%", "5,4%"):
            self.assertIn(value, current)
        self.assertIn("Ocupados: 1.130 (94,6%)", page.text("svg", id="current-pie"))
        self.assertIn("Vagos: 65 (5,4%)", page.text("svg", id="current-pie"))
        chart = page.one("svg", id="history-chart")
        table = page.one("table", id="history-values")
        rows = [n for n in page.matching("tr") if table in n["parents"]][1:]
        self.assertEqual(len(rows), 5)
        for index, month, label, occupied, vacant in (
            (0, "2026-09", "setembro de 2026", "1.109", "86"),
            (1, "2026-10", "outubro de 2026", "1.110", "85"),
            (2, "2026-11", "novembro de 2026", "1.120", "75"),
            (4, "2027-01", "janeiro de 2027", "1.130", "65"),
        ):
            cells = [n["text"] for n in page.nodes
                     if n["tag"] in ("th", "td") and rows[index] in n["parents"]]
            self.assertEqual(cells[:4], [label, occupied, vacant, "1.195"])
            self.assertIn(f"Ocupados: {occupied} — {label}", chart["text"])
            self.assertIn(f"Vagos: {vacant} — {label}", chart["text"])
            self.assertTrue([n for n in page.matching("a", href=resource_url(month))
                             if rows[index] in n["parents"]])
        self.assertIn("dezembro de 2026", rows[3]["text"])
        self.assertIn("Indisponível", rows[3]["text"])
        self.assertIn("dezembro de 2026: indisponível", chart["text"])
        for series in ("Ocupados", "Vagos"):
            lines = [n for n in page.matching("polyline", **{"aria-label": series})
                     if chart in n["parents"]]
            self.assertEqual(len(lines), 1)
            self.assertEqual(len(lines[0]["attrs"]["points"].split()), 3)
        self.assertEqual(json.loads((self.site / "data/history.json").read_text()), history)
        self.assertEqual((self.site / "data/status.json").read_bytes(),
                         (self.data / "status.json").read_bytes())

    def test_zero_counts_and_zero_total_do_not_invent_proportions_or_sectors(self):
        for occupied, vacant in ((0, 0), (1195, 0), (0, 1195)):
            with self.subTest(occupied=occupied, vacant=vacant):
                content = monthly_resource("2026-09", occupied, vacant)
                page = self.refresh(ControlledArchive({SEPTEMBER_URL: content}))
                table = page.text("table", id="current-values")
                self.assertIn("Ocupados", table)
                self.assertIn("Vagos", table)
                self.assertNotIn("nan", page.text("body").lower())
                self.assertNotIn("infinity", page.text("body").lower())
                if occupied + vacant == 0:
                    self.assertIn("Proporção indisponível: total aprovado igual a zero", page.text("body"))
                    self.assertFalse(page.matching("svg", id="current-pie"))
                    self.assertNotIn("%", table)
                    current_table = page.one("table", id="current-values")
                    self.assertEqual([n["text"] for n in page.matching("td")
                                      if current_table in n["parents"]],
                                     ["0", "—", "0", "—", "0", "—"])
                else:
                    self.assertIn("0,0%", table)
                    self.assertIn("100,0%", table)
                    pie = page.one("svg", id="current-pie")
                    disks = [n for n in page.matching("circle") if pie in n["parents"]]
                    self.assertEqual(len(disks), 1, "A 100% category must be a complete disk")
                    sectors = [n for n in page.matching("path")
                               if pie in n["parents"] and "fill" in n["attrs"]]
                    self.assertFalse(sectors, "Zero categories must not get a fake sector")
                chart = page.one("svg", id="history-chart")
                self.assertIn(f"Ocupados: {'1.195' if occupied else '0'} — setembro de 2026", chart["text"])
                self.assertIn(f"Vagos: {'1.195' if vacant else '0'} — setembro de 2026", chart["text"])

    def test_empty_first_import_and_later_invalid_source_never_publish_fake_data(self):
        with self.assertRaisesRegex(ValueError, "eligible|observation"):
            self.refresh(ControlledArchive({}))
        self.assertFalse(self.data.exists())
        self.assertFalse(self.site.exists())
        self.refresh()
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        content = variant(lambda table, header: table.remove(pf_classes(table, header)[-1]))
        with self.assertRaisesRegex(ValueError, "class|PCF"):
            self.refresh(ControlledArchive({SEPTEMBER_URL: content}),
                         clock=lambda: CHECK_TIME + timedelta(days=1))
        after = {path.relative_to(self.root): path.read_bytes()
                 for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)
        page = Page((self.site / "index.html").read_text())
        self.assertEqual(page.text("time", datetime="2026-09"), "setembro de 2026")
        self.assertIn("13/11/2026", page.text("time", datetime="2026-11-13T12:00:00Z"))

    def test_failed_incremental_candidate_preserves_dashboard_and_can_be_retried(self):
        self.refresh()
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        october_url = resource_url("2026-10")
        october = monthly_resource("2026-10", 1110, 85)
        corrected = monthly_resource("2026-09", 1109, 86)
        resources = {SEPTEMBER_URL: corrected, october_url: october}
        scenarios = (
            (ScriptedArchive({october_url: [TimeoutError("controlled outage")] * 3}, resources),
             "after 3 attempt"),
            (ControlledArchive({SEPTEMBER_URL: corrected, october_url: b"truncated ODS"}),
             "Invalid spreadsheet"),
        )
        for source, diagnostic in scenarios:
            with self.subTest(diagnostic=diagnostic):
                # September is valid but changed: no partial correction may leak out
                # when a subsequent resource fails download or validation.
                with self.assertRaisesRegex(ValueError, diagnostic) as failure:
                    self.refresh(source, clock=lambda: CHECK_TIME + timedelta(days=1))
                self.assertIn(october_url, str(failure.exception))
                after = {path.relative_to(self.root): path.read_bytes()
                         for path in self.root.rglob("*") if path.is_file()}
                self.assertEqual(after, before)
                page = Page((self.site / "index.html").read_text())
                self.assertEqual(page.text("time", datetime="2026-09"), "setembro de 2026")
                self.assertEqual(page.text("time", datetime="2026-11-13T12:00:00Z"),
                                 "13/11/2026 às 09:00 (Brasília, UTC−03:00)")
                self.assertIn("Ocupados: 1.108 (92,7%)", page.text("svg", id="current-pie"))
                self.assertIn("Vagos: 87 — setembro de 2026", page.text("svg", id="history-chart"))

        # Recovery uses the accepted history; no deletion or manual data repair.
        page = self.refresh(ControlledArchive(resources),
                            clock=lambda: CHECK_TIME + timedelta(days=2))
        self.assertEqual(page.text("time", datetime="2026-10"), "outubro de 2026")
        self.assertEqual(page.text("time", datetime="2026-11-15T12:00:00Z"),
                         "15/11/2026 às 09:00 (Brasília, UTC−03:00)")
        self.assertIn("Ocupados: 1.110 (92,9%)", page.text("svg", id="current-pie"))
        history = json.loads((self.site / "data/history.json").read_text())
        self.assertEqual([row["reference_month"] for row in history["observations"]],
                         ["2026-09", "2026-10"])
        self.assertEqual(len(history["corrections"]), 1)
        self.assertEqual(history["corrections"][0]["superseded"]["occupied"], 1108)
        self.assertEqual((self.site / "data/history.json").read_bytes(),
                         (self.data / "history.json").read_bytes())

    def test_complete_artifact_serves_local_assets_and_data_under_repository_subpath(self):
        self.site = self.root / "www" / "monitorar-vacancias-perito-pf"
        page = self.refresh()

        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0),
                                     partial(QuietHandler, directory=str(self.root / "www")))
        self.addCleanup(server.server_close)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}/monitorar-vacancias-perito-pf/"
        with urlopen(base) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("current-pie", response.read().decode())
        for node in page.nodes:
            for attr in ("href", "src"):
                value = node["attrs"].get(attr)
                if not value or value.startswith("#"):
                    continue
                if urlsplit(value).scheme:
                    self.assertEqual(node["tag"], "a", "No remote assets or runtime requests")
                    continue
                self.assertFalse(value.startswith("/"), "Root paths break repository Pages")
                with urlopen(urljoin(base, value)) as response:
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.read())
        for node in page.matching("svg"):
            for identifier in node["attrs"]["aria-labelledby"].split():
                self.assertTrue(page.text(id=identifier))
        self.assertEqual(page.one("a", href="#conteudo")["text"], "Ir para o conteúdo")
        self.assertEqual(page.one("main", id="conteudo")["attrs"].get("tabindex"), "-1",
                         "The skip link must move keyboard focus into the content")
        self.assertEqual(page.one("meta", name="viewport")["attrs"]["content"],
                         "width=device-width, initial-scale=1")


if __name__ == "__main__":
    unittest.main()
