"""Dashboard acceptance through the complete refresh/build operation."""
from datetime import timedelta
from functools import partial
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
    ARCHIVE_URL, CHECK_TIME, ControlledArchive, SEPTEMBER, SEPTEMBER_URL, TABLE,
    pf_classes, set_cell, variant,
)


def monthly_resource(month, occupied, vacant):
    """A controlled publication using the official sheet structure and identities."""
    def edit(table, header):
        for row in table.findall(TABLE + "table-row")[1:]:
            if "".join(row[header.index("ANO_MES")].itertext()).strip():
                set_cell(row, header, "ANO_MES", month.replace("-", ""))
        for index, row in enumerate(pf_classes(table, header)):
            for field, count in (("APROVADA", occupied + vacant), ("DISTRIBUIDA", occupied + vacant),
                                 ("OCUPADA", occupied), ("VAGA", vacant)):
                set_cell(row, header, field, count if index == 0 else 0)
    return variant(edit)


def resource_url(month):
    return ARCHIVE_URL + month[:4] + "/CargosVagosVacancias_" + month.replace("-", "") + ".ods"


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
