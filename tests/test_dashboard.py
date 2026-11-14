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
    monthly_resource as dated_resource, national_resources, pf_classes, resource_url, set_cell, variant,
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

    def axis_labels(self):
        chart = self.one("svg", id="history-chart")
        return [node["text"] for node in self.matching("text", **{"text-anchor": "end"})
                if chart in node["parents"]]


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

    def _after_leading_unavailable_gap(self, rows):
        self.assertEqual(len(rows), 20)
        self.assertIn("junho de 2025", rows[0]["text"])
        self.assertIn("agosto de 2026", rows[14]["text"])
        self.assertTrue(all("Indisponível" in row["text"] for row in rows[:15]))
        return rows[15:]

    def test_vacancy_headline_explains_official_counts_rate_and_distinct_dates(self):
        page = self.refresh()
        self.assertEqual(page.one("html")["attrs"]["lang"], "pt-BR")
        self.assertEqual(page.text("h1"), "Perito Criminal Federal — Polícia Federal")
        self.assertIn("Totais nacionais", page.text("body"))
        self.assertIn("todas as classes", page.text("body"))
        self.assertEqual(page.text("time", datetime="2026-09"), "setembro de 2026")
        self.assertEqual(page.text("time", datetime="2026-11-13T12:00:00Z"),
                         "13/11/2026 às 09:00 (Brasília, UTC−03:00)")
        self.assertIn("Última verificação bem-sucedida", page.text("body"))
        self.assertEqual(page.text("h2", id="current-title"), "Cargos vagos")
        self.assertEqual(page.text("dd", id="vacant-count"), "87")
        self.assertEqual(page.text("dd", id="vacancy-rate"), "7,3%")
        self.assertEqual([node["text"] for node in page.matching("dt")],
                         ["Cargos vagos", "Taxa de vacância"])
        table = page.one("table", id="current-values")
        self.assertEqual([n["text"] for n in page.matching("td") if table in n["parents"]],
                         ["1.108", "1.195"])
        self.assertIn("Ocupados", table["text"])
        self.assertIn("Total de cargos aprovados", table["text"])
        self.assertFalse(page.matching("svg", id="current-pie"))
        self.assertIn("aprovados em lei e não ocupados", page.text("body"))
        self.assertIn("não dados em tempo real", page.text("body"))
        self.assertIn("não representam vagas de concurso", page.text("body"))
        self.assertTrue(page.matching("a", href=SEPTEMBER_URL))
        self.assertTrue(page.matching("a", href="https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/gestao-de-pessoas-executivo-federal-cargos-vagos"))
        css = page.one("link", rel="stylesheet")["attrs"]["href"]
        self.assertFalse(css.startswith(("/", "http:", "https:")))
        self.assertTrue((self.site / css).is_file())
        self.assertEqual(json.loads((self.site / "data/history.json").read_text()),
                         json.loads((self.data / "history.json").read_text()))

    def test_headline_rate_uses_same_month_approved_total_not_distributed_posts(self):
        def different_distribution(table, header):
            for index, row in enumerate(pf_classes(table, header)):
                set_cell(row, header, "DISTRIBUIDA", 500 if index == 0 else 0)
        publication = variant(different_distribution, monthly_resource("2025-06", 900, 100))
        page = self.refresh(ControlledArchive({resource_url("2025-06"): publication}))
        self.assertEqual(page.text("time", datetime="2025-06"), "junho de 2025")
        self.assertEqual(page.text("dd", id="vacant-count"), "100")
        self.assertEqual(page.text("dd", id="vacancy-rate"), "10,0%")
        table = page.one("table", id="current-values")
        self.assertEqual([n["text"] for n in page.matching("td") if table in n["parents"]],
                         ["900", "1.000"])
        self.assertEqual(json.loads((self.site / "data/history.json").read_text())[
            "observations"][0]["distributed"], 500)

    def test_one_official_month_is_a_vacancy_point_on_its_own_zero_based_count_axis(self):
        page = self.refresh()
        chart = page.one("svg", id="history-chart")
        self.assertEqual(chart["attrs"]["role"], "img")
        self.assertIn("history-description", chart["attrs"]["aria-labelledby"])
        self.assertIn("Mês de referência oficial", chart["text"])
        self.assertIn("Cargos vagos (quantidade)", chart["text"])
        self.assertIn("set/2026", chart["text"])
        self.assertNotIn("Ocupados", chart["text"])
        self.assertIn("Vagos: 87 — setembro de 2026", chart["text"])
        self.assertEqual(page.axis_labels(), ["0", "30", "60", "90", "120"])
        self.assertFalse([n for n in page.matching("circle") if chart in n["parents"]])
        self.assertEqual(len([n for n in page.matching("rect") if chart in n["parents"]]), 1)
        self.assertFalse([n for n in page.matching("polyline") if chart in n["parents"]])
        self.assertIn("Apenas um mês disponível", page.text("body"))
        self.assertIn("Novos pontos aparecerão", page.text("body"))
        table = page.text("table", id="history-values")
        for expected in ("setembro de 2026", "1.108", "87", "1.195", "Planilha oficial"):
            self.assertIn(expected, table)
        self.assertTrue(all(n["attrs"].get("scope") in ("col", "row")
                            for n in page.matching("th")))

    def test_only_calendar_month_is_a_centered_zero_point_without_an_invented_line(self):
        page = self.refresh(ControlledArchive({
            resource_url("2025-06"): monthly_resource("2025-06", 1195, 0),
        }))
        self.assertEqual(page.text("dd", id="vacant-count"), "0")
        self.assertEqual(page.text("dd", id="vacancy-rate"), "0,0%")
        chart = page.one("svg", id="history-chart")
        self.assertIn("Apenas um mês disponível", chart["text"])
        points = [n for n in page.matching("rect") if chart in n["parents"]]
        self.assertEqual(len(points), 1)
        self.assertEqual(float(points[0]["attrs"]["x"]) + 4, 470)
        self.assertEqual(float(points[0]["attrs"]["y"]) + 4, 270)
        self.assertIn("Vagos: 0 — junho de 2025", points[0]["text"])
        self.assertFalse([n for n in page.matching("polyline") if chart in n["parents"]])
        self.assertNotIn("indisponível", chart["text"])
        table = page.one("table", id="history-values")
        self.assertEqual([n["text"] for n in page.matching("td") if table in n["parents"]],
                         ["1.195", "0", "1.195", "Planilha oficial (ODS) — junho de 2025"])

    def test_history_uses_monthly_axis_and_breaks_the_vacancy_line_at_missing_months(self):
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
        rows = self._after_leading_unavailable_gap(rows)
        self.assertEqual(len(rows), 5)
        for row, label in zip(rows, ("setembro de 2026", "outubro de 2026", "novembro de 2026",
                                     "dezembro de 2026", "janeiro de 2027")):
            self.assertIn(label, row["text"])
        self.assertIn("Indisponível", rows[2]["text"])
        self.assertNotIn("0", rows[2]["text"].replace("novembro de 2026", ""))
        squares = [n for n in page.matching("rect") if chart in n["parents"]]
        self.assertEqual(len(squares), 4)
        # Equal month spacing, including the missing November slot (not compressed away).
        xs = [float(n["attrs"]["x"]) + 4 for n in squares]
        self.assertAlmostEqual(xs[1] - xs[0], xs[3] - xs[2])
        self.assertAlmostEqual(xs[2] - xs[1], 2 * (xs[1] - xs[0]))
        lines = [n for n in page.matching("polyline", **{"aria-label": "Vagos"})
                 if chart in n["parents"]]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(n["attrs"]["points"].split()) == 2 for n in lines))
        self.assertTrue(lines[0]["attrs"].get("stroke-dasharray"))
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
        self.assertIn("1.109", page.text("table", id="history-values"))
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
        for value in ("1.130", "1.195"):
            self.assertIn(value, current)
        self.assertEqual(page.text("dd", id="vacant-count"), "65")
        self.assertEqual(page.text("dd", id="vacancy-rate"), "5,4%")
        chart = page.one("svg", id="history-chart")
        table = page.one("table", id="history-values")
        rows = [n for n in page.matching("tr") if table in n["parents"]][1:]
        rows = self._after_leading_unavailable_gap(rows)
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
            self.assertIn(f"Vagos: {vacant} — {label}", chart["text"])
            self.assertTrue([n for n in page.matching("a", href=resource_url(month))
                             if rows[index] in n["parents"]])
        self.assertIn("dezembro de 2026", rows[3]["text"])
        self.assertIn("Indisponível", rows[3]["text"])
        self.assertIn("dezembro de 2026: indisponível", chart["text"])
        lines = [n for n in page.matching("polyline", **{"aria-label": "Vagos"})
                 if chart in n["parents"]]
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0]["attrs"]["points"].split()), 3)
        self.assertEqual(json.loads((self.site / "data/history.json").read_text()), history)
        self.assertEqual((self.site / "data/status.json").read_bytes(),
                         (self.data / "status.json").read_bytes())

    def test_authentic_national_backfill_matches_all_fifteen_months_and_keeps_july_gap(self):
        # Independent literal research expectations, not calculated from input rows.
        expected = [
            ("2025-06", 1195, 1195, 1116, 79),
            ("2025-08", 1195, 1195, 1111, 84),
            ("2025-09", 1195, 1195, 1108, 87),
            ("2025-10", 1195, 1195, 1102, 93),
            ("2025-11", 1195, 1195, 1101, 94),
            ("2025-12", 1195, 1195, 1096, 99),
            ("2026-01", 1195, 1195, 1094, 101),
            ("2026-02", 1195, 1195, 1090, 105),
            ("2026-03", 1195, 1195, 1089, 106),
            ("2026-04", 1195, 1195, 1085, 110),
            ("2026-05", 1195, 1195, 1083, 112),
            ("2026-06", 1195, 1195, 1083, 112),
            ("2026-07", 1195, 1195, 1074, 121),
            ("2026-08", 1195, 1195, 1067, 128),
            ("2026-09", 1195, 1195, 1108, 87),
        ]
        labels = ("junho de 2025", "agosto de 2025", "setembro de 2025",
                  "outubro de 2025", "novembro de 2025", "dezembro de 2025",
                  "janeiro de 2026", "fevereiro de 2026", "março de 2026",
                  "abril de 2026", "maio de 2026", "junho de 2026",
                  "julho de 2026", "agosto de 2026", "setembro de 2026")
        self.refresh()
        september = json.loads((self.data / "history.json").read_text())["observations"][0]
        resources = national_resources()
        page = self.refresh(ControlledArchive(resources),
                            clock=lambda: CHECK_TIME + timedelta(days=1))
        history = json.loads((self.data / "history.json").read_text())
        observations = history["observations"]
        self.assertEqual([tuple(row[key] for key in
                                ("reference_month", "authorized", "distributed", "occupied", "vacant"))
                          for row in observations], expected)
        self.assertEqual(observations[-1], september, "Backfill must not renew September provenance")
        self.assertEqual(history.get("corrections", []), [])
        self.assertEqual(page.text("time", datetime="2026-09"), "setembro de 2026")
        self.assertIn("1.108", page.text("table", id="current-values"))
        self.assertIn("Histórico a partir de junho de 2025", page.text("body"))
        chart = page.one("svg", id="history-chart")
        # The scrollable timeline must not scale its 15px labels down as months grow.
        minimum_width = float(chart["attrs"]["style"].split(":")[1].strip().removesuffix("px"))
        self.assertGreaterEqual(minimum_width, float(chart["attrs"]["viewbox"].split()[2]),
                                "Keep chart labels at their intended size; scroll instead of shrinking")
        table = page.one("table", id="history-values")
        rows = [n for n in page.matching("tr") if table in n["parents"]][1:]
        self.assertEqual(len(rows), 16)
        self.assertIn("julho de 2025", rows[1]["text"])
        self.assertIn("Indisponível", rows[1]["text"])
        self.assertFalse([n for n in page.matching("td")
                          if rows[1] in n["parents"] and n["text"].strip() == "0"])
        self.assertFalse([n for n in page.matching("a") if rows[1] in n["parents"]])
        self.assertIn("julho de 2025: indisponível", chart["text"])
        accepted_rows = rows[:1] + rows[2:]
        for row, observation, counts, label in zip(accepted_rows, observations, expected, labels):
            cells = [n["text"] for n in page.nodes
                     if n["tag"] in ("th", "td") and row in n["parents"]]
            occupied = f"{counts[3]:,}".replace(",", ".")
            self.assertEqual(cells[:4], [label, occupied, str(counts[4]), "1.195"])
            self.assertIn(f"Vagos: {counts[4]} — {label}", chart["text"])
            url = observation["source"]["url"]
            self.assertIn(url, resources, "Source casing must remain as actually published")
            self.assertTrue([n for n in page.matching("a", href=url) if row in n["parents"]])
            self.assertEqual(observation["source"]["sha256"], hashlib.sha256(resources[url]).hexdigest())
        self.assertNotIn("Ocupados", chart["text"])
        self.assertEqual(page.axis_labels(), ["0", "40", "80", "120", "160"])
        squares = [n for n in page.matching("rect") if chart in n["parents"]]
        self.assertEqual(len(squares), 15)
        xs = [float(n["attrs"]["x"]) + 4 for n in squares]
        self.assertAlmostEqual(xs[1] - xs[0], 2 * (xs[2] - xs[1]))
        lines = [n for n in page.matching("polyline", **{"aria-label": "Vagos"})
                 if chart in n["parents"]]
        self.assertEqual(len(lines), 1)
        vertices = [tuple(map(float, point.split(",")))
                    for point in lines[0]["attrs"]["points"].split()]
        markers = [(float(n["attrs"]["x"]) + 4, float(n["attrs"]["y"]) + 4) for n in squares]
        self.assertEqual(len(vertices), 14, "The isolated June point must not connect across July")
        for vertex, marker in zip(vertices, markers[1:]):
            self.assertAlmostEqual(vertex[0], marker[0])
            self.assertAlmostEqual(vertex[1], marker[1])
        before = (self.data / "history.json").read_bytes()
        self.refresh(ControlledArchive(resources), clock=lambda: CHECK_TIME + timedelta(days=2))
        self.assertEqual((self.data / "history.json").read_bytes(), before)
        self.assertEqual((self.site / "data/history.json").read_bytes(), before)
        self.assertEqual((self.site / "data/status.json").read_bytes(),
                         (self.data / "status.json").read_bytes())
        self.assertEqual(json.loads((self.data / "status.json").read_text())[
            "last_successful_check"], "2026-11-15T12:00:00Z")

    def test_all_zero_vacancy_history_keeps_a_legible_axis_and_distinguishes_the_gap(self):
        page = self.refresh(ControlledArchive({
            resource_url("2025-06"): monthly_resource("2025-06", 1195, 0),
            resource_url("2025-08"): monthly_resource("2025-08", 1195, 0),
            resource_url("2025-09"): monthly_resource("2025-09", 1195, 0),
        }))
        chart = page.one("svg", id="history-chart")
        self.assertEqual(page.axis_labels(), ["0", "1", "2", "3", "4"])
        points = [n for n in page.matching("rect") if chart in n["parents"]]
        self.assertEqual(len(points), 3)
        self.assertEqual([float(n["attrs"]["y"]) + 4 for n in points], [270, 270, 270])
        lines = [n for n in page.matching("polyline") if chart in n["parents"]]
        self.assertEqual(len(lines), 1)
        vertices = [tuple(map(float, point.split(",")))
                    for point in lines[0]["attrs"]["points"].split()]
        self.assertEqual(len(vertices), 2, "June must stay isolated across the unavailable July slot")
        for vertex, marker in zip(vertices, points[1:]):
            self.assertAlmostEqual(vertex[0], float(marker["attrs"]["x"]) + 4)
            self.assertEqual(vertex[1], 270)
        table = page.one("table", id="history-values")
        rows = [n for n in page.matching("tr") if table in n["parents"]][1:]
        self.assertEqual(len(rows), 4)
        self.assertIn("julho de 2025", rows[1]["text"])
        self.assertIn("Indisponível", rows[1]["text"])
        self.assertFalse([n for n in page.matching("td")
                          if rows[1] in n["parents"] and n["text"].strip() == "0"])
        self.assertEqual(page.text("dd", id="vacant-count"), "0")
        self.assertEqual(page.text("dd", id="vacancy-rate"), "0,0%")

    def test_zero_counts_and_zero_total_keep_true_zero_and_an_honest_headline_rate(self):
        for occupied, vacant, rate in ((0, 0, "—"), (1195, 0, "0,0%"), (0, 1195, "100,0%")):
            with self.subTest(occupied=occupied, vacant=vacant):
                content = monthly_resource("2026-09", occupied, vacant)
                page = self.refresh(ControlledArchive({SEPTEMBER_URL: content}))
                self.assertEqual(page.text("dd", id="vacant-count"), "1.195" if vacant else "0")
                self.assertEqual(page.text("dd", id="vacancy-rate"), rate)
                table = page.one("table", id="current-values")
                self.assertIn("Ocupados", table["text"])
                self.assertEqual([n["text"] for n in page.matching("td") if table in n["parents"]],
                                 ["1.195" if occupied else "0", "1.195" if occupied or vacant else "0"])
                self.assertFalse(page.matching("svg", id="current-pie"))
                self.assertNotIn("nan", page.text("body").lower())
                self.assertNotIn("infinity", page.text("body").lower())
                if occupied + vacant == 0:
                    self.assertIn("Taxa indisponível: total aprovado igual a zero", page.text("body"))
                    self.assertNotIn("%", page.one("section", **{"aria-labelledby": "current-title"})["text"])
                chart = page.one("svg", id="history-chart")
                self.assertIn(f"Vagos: {'1.195' if vacant else '0'} — setembro de 2026", chart["text"])
                if not vacant:
                    point = [n for n in page.matching("rect") if chart in n["parents"]][0]
                    self.assertEqual(float(point["attrs"]["y"]) + 4, 270)
                    self.assertEqual(page.axis_labels(), ["0", "1", "2", "3", "4"])

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
        accepted = national_resources()
        self.refresh(ControlledArchive(accepted))
        accepted_history = json.loads((self.data / "history.json").read_text())["observations"]
        self.assertEqual(len(accepted_history), 15)
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        october_url = resource_url("2026-10")
        october = monthly_resource("2026-10", 1110, 85)
        corrected = monthly_resource("2026-09", 1109, 86)
        resources = {**accepted, SEPTEMBER_URL: corrected, october_url: october}
        scenarios = (
            (ScriptedArchive({october_url: [TimeoutError("controlled outage")] * 3}, resources),
             "after 3 attempt"),
            (ControlledArchive({**resources, october_url: b"truncated ODS"}),
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
                self.assertIn("1.108", page.text("table", id="current-values"))
                self.assertEqual(page.text("dd", id="vacant-count"), "87")
                self.assertEqual(page.text("dd", id="vacancy-rate"), "7,3%")
                self.assertIn("Vagos: 87 — setembro de 2026", page.text("svg", id="history-chart"))

        # Recovery uses the accepted history; no deletion or manual data repair.
        page = self.refresh(ControlledArchive(resources),
                            clock=lambda: CHECK_TIME + timedelta(days=2))
        self.assertEqual(page.text("time", datetime="2026-10"), "outubro de 2026")
        self.assertEqual(page.text("time", datetime="2026-11-15T12:00:00Z"),
                         "15/11/2026 às 09:00 (Brasília, UTC−03:00)")
        self.assertIn("1.110", page.text("table", id="current-values"))
        self.assertEqual(page.text("dd", id="vacant-count"), "85")
        self.assertEqual(page.text("dd", id="vacancy-rate"), "7,1%")
        history = json.loads((self.site / "data/history.json").read_text())
        self.assertEqual([row["reference_month"] for row in history["observations"]],
                         [row["reference_month"] for row in accepted_history] + ["2026-10"])
        self.assertEqual(history["observations"][:-2], accepted_history[:-1],
                         "Retry must preserve all fourteen unchanged historical observations")
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
            self.assertIn("vacant-count", response.read().decode())
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
