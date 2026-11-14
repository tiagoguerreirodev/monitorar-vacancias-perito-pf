"""Optional real-mouse acceptance via Orca, not a headless/CI test.

Prepare uses the public refresh/build seam with controlled official documents.
Check accepts an explicitly owned page and local preview; never creates/closes tabs.
DOM evaluation only measures/reads the page or changes scroll position. Inspection
itself must be caused by `orca mouse move`, never synthetic events or handlers.
See docs/operations.md for the local recipe.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit
from urllib.request import urlopen

from perito_dashboard import refresh_and_build
from tests.sources import CHECK_TIME, ControlledArchive, national_resources, resource_url
from tests.test_dashboard import monthly_resource


class Browser:
    def __init__(self, executable, page, url):
        self.executable, self.page, self.url = executable, page, url

    def command(self, *args):
        command = [self.executable, *args, "--page", self.page, "--json"]
        if args[0] not in {"viewport", "wait"}:  # No URL guard on these in this Orca.
            command.extend(["--expect-url", self.url])
        completed = subprocess.run(command, text=True, capture_output=True)
        if completed.returncode:
            raise AssertionError((command, completed.stdout, completed.stderr))
        receipt = json.loads(completed.stdout)
        if receipt.get("error"):
            raise AssertionError(receipt)
        return receipt["result"]

    def evaluate(self, expression):
        result = self.command("eval", "--expression", expression)["result"]
        try:
            return json.loads(result) if result is not None else None
        except json.JSONDecodeError:  # Orca returns strings without JSON quoting.
            return result

    def move(self, x, y):
        return self.command("mouse", "move", "--x", str(x), "--y", str(y))

    def setup(self, width=1440, height=1000):
        self.command("viewport", "--width", str(width), "--height", str(height))
        self.evaluate("document.querySelector('#history-chart').scrollIntoView({block:'center'}); "
                      "document.querySelector('.chart-scroll').scrollLeft = 0")

    def point(self, fraction, height):
        # Ordinary visible grid geometry, not application metadata or a helper API.
        return self.evaluate(f"""(() => {{
          const svg = document.querySelector('#history-chart');
          const lines = svg.querySelectorAll('.grid-line');
          const first = lines[0], last = lines[lines.length - 1];
          const p = svg.createSVGPoint();
          p.x = first.x1.baseVal.value + {fraction} *
                (first.x2.baseVal.value - first.x1.baseVal.value);
          p.y = last.y1.baseVal.value + {height} *
                (first.y1.baseVal.value - last.y1.baseVal.value);
          const screen = p.matrixTransform(svg.getScreenCTM());
          return {{x: screen.x, y: screen.y}};
        }})()""")

    def tooltip(self):
        return self.evaluate("""(() => {
          const tooltip = document.querySelector('[role="tooltip"]');
          return tooltip && !tooltip.hidden && getComputedStyle(tooltip).display !== 'none'
            ? tooltip.textContent.trim() : null;
        })()""")

    def inspect(self, fraction, height, expected):
        point = self.point(fraction, height)
        self.move(point["x"], point["y"])
        observed = self.tooltip()
        assert observed == expected, (expected, observed, point)
        print(f"PASS mouse ({point['x']:.2f}, {point['y']:.2f}): {observed}")

    def content(self):
        return self.evaluate("""(() => {
          const chart = document.querySelector('#history-chart');
          return {count: document.querySelector('#vacant-count').textContent,
                  rate: document.querySelector('#vacancy-rate').textContent,
                  reference: document.querySelector('.reference time').getAttribute('datetime'),
                  checked: document.querySelector('.context time').getAttribute('datetime'),
                  checkedText: document.querySelector('.context time').textContent,
                  context: document.querySelector('#current-values').textContent,
                  explanation: document.querySelector('main').textContent,
                  ticks: Array.from(chart.querySelectorAll('text[text-anchor="end"]'))
                    .map(node => node.textContent),
                  rows: Array.from(document.querySelector('#history-values').tBodies[0].rows)
                    .map(row => Array.from(row.cells).map(cell => cell.textContent)),
                  sources: Array.from(document.querySelectorAll('main a[href]'))
                    .map(link => link.getAttribute('href')),
                  markers: chart.querySelectorAll('.vacant-point').length,
                  lines: chart.querySelectorAll('polyline').length,
                  pageWidth: document.documentElement.scrollWidth, width: innerWidth};
        })()""")

    def guide(self, fraction):
        geometry = self.evaluate("""(() => {
          const guide = document.querySelector('.inspection-guide');
          const grid = document.querySelector('#history-chart .grid-line');
          return {visible: getComputedStyle(guide).display !== 'none',
                  x: guide.x1.baseVal.value, x2: guide.x2.baseVal.value,
                  left: grid.x1.baseVal.value, right: grid.x2.baseVal.value,
                  top: guide.y1.baseVal.value, bottom: guide.y2.baseVal.value};
        })()""")
        expected = geometry['left'] + fraction * (geometry['right'] - geometry['left'])
        assert geometry['visible'] and abs(geometry['x'] - expected) < .01, geometry
        assert geometry['x'] == geometry['x2'], geometry
        assert (geometry['top'], geometry['bottom']) == (30, 270), geometry
        print("PASS visible calendar guide", geometry)

    def contained(self):
        geometry = self.evaluate("""(() => {
          const tip = document.querySelector('[role="tooltip"]').getBoundingClientRect();
          const clip = document.querySelector('.chart-scroll').getBoundingClientRect();
          return {left: tip.left, right: tip.right, top: tip.top, bottom: tip.bottom,
                  clipLeft: Math.max(0, clip.left),
                  clipRight: Math.min(innerWidth, clip.right), height: innerHeight,
                  pageWidth: document.documentElement.scrollWidth, width: innerWidth,
                  fontSize: parseFloat(getComputedStyle(document.querySelector('[role="tooltip"]')).fontSize),
                  textFits: document.querySelector('[role="tooltip"]').scrollWidth <=
                            document.querySelector('[role="tooltip"]').clientWidth};
        })()""")
        assert geometry["fontSize"] >= 16 and geometry["textFits"], geometry
        assert geometry["left"] >= geometry["clipLeft"], geometry
        assert geometry["right"] <= geometry["clipRight"], geometry
        assert 0 <= geometry["top"] <= geometry["bottom"] <= geometry["height"], geometry
        assert geometry["pageWidth"] == geometry["width"], geometry
        print("PASS tooltip contained/readable without page overflow", geometry)

    def leave(self):
        point = self.point(.5, -.03)
        point["x"] = self.evaluate("""(() => {
          const clip = document.querySelector('.chart-scroll').getBoundingClientRect();
          return (clip.left + clip.right) / 2;
        })()""")
        self.move(point["x"], point["y"])
        assert self.tooltip() is None, ("Stale inspection after leaving plot", self.tooltip())
        assert self.evaluate("getComputedStyle(document.querySelector('.inspection-guide')).display") == 'none'
        print("PASS leaving plot clears inspection and guide")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--root", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--orca", required=True, help="Executable resolved by the Orca skill")
    check.add_argument("--page", required=True, help="Your explicitly owned browser page ID")
    check.add_argument("--base-url", required=True, help="Local preview root, ending in /")
    check.add_argument("--case", choices=["nearest", "gap", "leave", "clamp", "scroll", "resize",
                                         "edges", "zero", "narrow", "formatted", "fallback", "allzero",
                                         "summary", "single", "sparse"],
                       default="nearest")
    args = parser.parse_args()
    if args.command == "prepare":
        refresh_and_build(args.root / "data-national",
                          args.root / "www/national/monitorar-vacancias-perito-pf",
                          source=ControlledArchive(national_resources()), clock=lambda: CHECK_TIME)
        refresh_and_build(args.root / "data-zero",
                          args.root / "www/zero/monitorar-vacancias-perito-pf",
                          source=ControlledArchive({resource_url("2025-06"):
                                                    monthly_resource("2025-06", 1195, 0)}),
                          clock=lambda: CHECK_TIME)
        refresh_and_build(args.root / "data-formatted",
                          args.root / "www/formatted/monitorar-vacancias-perito-pf",
                          source=ControlledArchive({
                              resource_url("2025-06"): monthly_resource("2025-06", 50, 12345),
                              resource_url("2025-08"): monthly_resource("2025-08", 1195, 0),
                          }), clock=lambda: CHECK_TIME)
        refresh_and_build(args.root / "data-allzero",
                          args.root / "www/allzero/monitorar-vacancias-perito-pf",
                          source=ControlledArchive({resource_url(month): monthly_resource(month, 0, 0)
                                                    for month in ("2025-06", "2025-08", "2025-09")}),
                          clock=lambda: CHECK_TIME)
        for name, values in (("single", (("2025-06", 108, 12),)),
                             ("sparse", (("2025-06", 108, 12), ("2025-09", 120, 0),
                                         ("2027-02", 95, 25)))):
            refresh_and_build(args.root / f"data-{name}",
                              args.root / f"www/{name}/monitorar-vacancias-perito-pf",
                              source=ControlledArchive({resource_url(month): monthly_resource(month, occupied, vacant)
                                                        for month, occupied, vacant in values}),
                              clock=lambda: CHECK_TIME)
        fallback = args.root / "www/fallback/monitorar-vacancias-perito-pf"
        shutil.copytree(args.root / "www/national/monitorar-vacancias-perito-pf",
                        fallback, dirs_exist_ok=True)
        (fallback / "assets/inspection.js").unlink()  # Simulate an unavailable optional asset.
        print(args.root / "www")
        return
    assert urlsplit(args.base_url).hostname in {"127.0.0.1", "localhost"}, "Local preview only"
    assert args.page != "fff658ce-af08-4721-b944-f11fa526a5c0", "Protected user page"
    fixture = args.case if args.case in {"zero", "formatted", "fallback", "allzero", "single", "sparse"} else "national"
    url = args.base_url.rstrip("/") + f"/{fixture}/monitorar-vacancias-perito-pf/"
    browser = Browser(args.orca, args.page, url)
    browser.setup(width=320 if args.case == "narrow" else 1440,
                  height=800 if args.case == "narrow" else 1000)
    if args.case == "summary":
        for width in (1440, 320):
            browser.command("viewport", "--width", str(width), "--height", "1000")
            content = browser.content()
            assert (content['count'], content['rate'], content['reference']) == ('87', '7,3%', '2026-09'), content
            assert content['checked'] == '2026-11-13T12:00:00Z', content
            assert content['checkedText'] == '13/11/2026 às 09:00 (Brasília, UTC−03:00)', content
            assert '1.108' in content['context'] and '1.195' in content['context'], content
            assert content['ticks'] == ['0', '40', '80', '120', '160'], content
            assert (content['markers'], content['lines']) == (15, 1), content
            assert [row[2] if len(row) == 5 else None for row in content['rows']] == [
                '79', None, '84', '87', '93', '94', '99', '101', '105', '106', '110',
                '112', '112', '121', '128', '87'], content
            assert content['pageWidth'] == width, content
            assert 'não representam vagas de concurso' in content['explanation'], content
            assert 'A data da verificação não é a referência dos cargos.' in content['explanation'], content
            assert 'data/history.json' in content['sources'] and 'data/status.json' in content['sources'], content
            assert ('https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/'
                    'gestao-de-pessoas-executivo-federal-cargos-vagos') in content['sources'], content
        # Read the public local bytes, not application state; digest the external document.
        with urlopen(url + 'data/history.json') as response:
            history = json.load(response)
        with urlopen(url + 'data/status.json') as response:
            status = json.load(response)
        current = history['observations'][-1]
        source = 'https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/2026/CargosVagosVacancias_202609.ods'
        assert (current['reference_month'], current['occupied'], current['vacant'], current['authorized']) == (
            '2026-09', 1108, 87, 1195), current
        assert current['source']['url'] == source and source in content['sources'], current
        assert current['source']['sha256'] == sha256(national_resources()[source]).hexdigest(), current
        assert current['source']['retrieved_at'] == status['last_successful_check'] == '2026-11-13T12:00:00Z'
        print('PASS desktop/320px header, same-reference rate/context, vacancy axis/table, check vs reference and source bytes')
        return
    if args.case == "single":
        content = browser.content()
        assert (content['count'], content['rate'], content['reference']) == ('12', '10,0%', '2025-06'), content
        assert content['ticks'] == ['0', '3', '6', '9', '12'], content
        assert (content['markers'], content['lines']) == (1, 0), content
        assert content['rows'][0][:4] == ['junho de 2025', '108', '12', '120'], content
        assert 'um único ponto de cargos vagos, sem tendência' in content['explanation'], content
        for fraction, height in ((0, .08), (.5, .92), (1, .08)):
            browser.inspect(fraction, height, 'junho de 2025 — Cargos vagos: 12')
            browser.guide(.5)
            browser.contained()
        browser.leave()
        print('PASS single positive observation without invented trend')
        return
    if args.case == "sparse":
        content = browser.content()
        assert (content['markers'], content['lines'], len(content['rows'])) == (3, 0, 21), content
        assert content['ticks'] == ['0', '7', '14', '21', '28'], content
        for fraction, expected in ((1 / 20, 'julho de 2025 — dados indisponíveis'),
                                   (2 / 20, 'agosto de 2025 — dados indisponíveis'),
                                   (3 / 20, 'setembro de 2025 — Cargos vagos: 0')):
            browser.inspect(fraction, .08, expected)
            browser.inspect(fraction, .92, expected)
            browser.guide(fraction)
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
        browser.inspect(19 / 20, .08, 'janeiro de 2027 — dados indisponíveis')
        browser.guide(19 / 20)
        browser.inspect(1, .92, 'fevereiro de 2027 — Cargos vagos: 25')
        browser.guide(1)
        browser.contained()
        browser.leave()
        print('PASS consecutive/new-year gaps never bridge or fabricate zero')
        return
    if args.case == "narrow":
        browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 79")
        browser.inspect(1 / 15 - .002, .92, "julho de 2025 — dados indisponíveis")
        browser.contained()
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
        browser.command("wait", "--text", "setembro de 2026 — Cargos vagos: 87")
        assert browser.tooltip() == "setembro de 2026 — Cargos vagos: 87", browser.tooltip()
        browser.inspect(1, .08, "setembro de 2026 — Cargos vagos: 87")
        browser.contained()
        # Move the plot near the bottom of the viewport through ordinary page scrolling.
        bottom = browser.point(1, .92)
        browser.evaluate(f"window.scrollBy(0, {bottom['y']} - (innerHeight - 12))")
        browser.inspect(1, .92, "setembro de 2026 — Cargos vagos: 87")
        browser.contained()
        browser.leave()
        return
    if args.case == "fallback":
        point = browser.point(3 / 15, .08)
        browser.move(point["x"], point["y"])
        assert browser.tooltip() is None, "Optional script should be unavailable"
        static = browser.evaluate("""(() => {
          const chart = document.querySelector('#history-chart');
          const table = document.querySelector('#history-values');
          return {title: chart.querySelector('title').textContent,
                  markers: chart.querySelectorAll('.vacant-point').length,
                  descriptions: chart.querySelector('desc').textContent,
                  rows: table.tBodies[0].rows.length, table: table.textContent,
                  scrollers: Array.from(document.querySelectorAll('[role="region"]'))
                    .map(region => region.tabIndex)};
        })()""")
        assert static["title"] == "Histórico de cargos vagos", static
        assert static["markers"] == 15 and static["rows"] == 16, static
        assert "julho de 2025: indisponível" in static["descriptions"], static
        assert "setembro de 2026" in static["table"] and "87" in static["table"], static
        assert static["scrollers"] == [0, 0], static
        browser.setup(width=320, height=800)
        point = browser.point(0, .08)
        browser.move(point['x'], point['y'])
        assert browser.tooltip() is None, 'No enhancement should appear on mobile either'
        scroll = browser.evaluate("""(() => {
          const regions = Array.from(document.querySelectorAll('[role="region"]'));
          regions.forEach(region => { region.scrollLeft = 99999; });
          return {offsets: regions.map(region => region.scrollLeft),
                  names: regions.map(region => region.getAttribute('aria-label')),
                  pageWidth: document.documentElement.scrollWidth, pageX: scrollX};
        })()""")
        assert all(offset > 0 for offset in scroll['offsets']), scroll
        assert all(scroll['names']) and scroll['pageWidth'] == 320 and scroll['pageX'] == 0, scroll
        print("PASS unavailable JS leaves useful static chart, equivalent table and named tab stops; independent 320px scrollers", scroll)
        return
    if args.case == "allzero":
        content = browser.content()
        assert (content['count'], content['rate'], content['reference']) == ('0', '—', '2025-09'), content
        assert 'Taxa indisponível: total aprovado igual a zero.' in content['explanation'], content
        assert content['ticks'] == ['0', '1', '2', '3', '4'], content
        assert (content['markers'], content['lines']) == (3, 1), content
        browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 0")
        browser.inspect(1 / 3, .92, "julho de 2025 — dados indisponíveis")
        browser.guide(1 / 3)
        browser.inspect(2 / 3, .08, "agosto de 2025 — Cargos vagos: 0")
        browser.inspect(1, .92, "setembro de 2025 — Cargos vagos: 0")
        browser.contained()
        browser.leave()
        return
    if args.case == "formatted":
        browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 12.345")
        browser.inspect(.5, .92, "julho de 2025 — dados indisponíveis")
        browser.inspect(1, .08, "agosto de 2025 — Cargos vagos: 0")
        browser.contained()
        browser.command("viewport", "--width", "1000", "--height", "1000")
        browser.inspect(.5, .08, "julho de 2025 — dados indisponíveis")
        browser.inspect(0, .92, "junho de 2025 — Cargos vagos: 12.345")
        browser.contained()
        browser.leave()
        return
    if args.case == "zero":
        for fraction, height in ((0, .08), (.5, .92), (1, .08)):
            browser.inspect(fraction, height, "junho de 2025 — Cargos vagos: 0")
            browser.contained()
        browser.leave()
        return
    # September 2025 is slot 3 of 16, away from every marker/line vertically.
    browser.inspect(3 / 15, .08, "setembro de 2025 — Cargos vagos: 87")
    if args.case == "gap":
        browser.inspect(1 / 15, .08, "julho de 2025 — dados indisponíveis")
        browser.inspect(1 / 15, .92, "julho de 2025 — dados indisponíveis")
        browser.guide(1 / 15)
        browser.inspect(2 / 15, .92, "agosto de 2025 — Cargos vagos: 84")
    if args.case == "leave":
        browser.leave()
    if args.case == "clamp":
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
        browser.inspect(1, .92, "setembro de 2026 — Cargos vagos: 87")
        browser.contained()
    if args.case == "scroll":
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 341.333333")
        browser.command("wait", "--text", "janeiro de 2026 — Cargos vagos: 101")
        assert browser.tooltip() == "janeiro de 2026 — Cargos vagos: 101", browser.tooltip()
        browser.contained()
        browser.inspect(14 / 15, .08, "agosto de 2026 — Cargos vagos: 128")
    if args.case == "edges":
        browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 79")
        browser.inspect(7.5 / 15 - .001, .92, "janeiro de 2026 — Cargos vagos: 101")
        browser.inspect(7.5 / 15, .08, "fevereiro de 2026 — Cargos vagos: 105")
        browser.inspect(7.5 / 15 + .001, .92, "fevereiro de 2026 — Cargos vagos: 105")
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
        browser.inspect(1, .08, "setembro de 2026 — Cargos vagos: 87")
        browser.leave()
    if args.case == "resize":
        browser.command("viewport", "--width", "1200", "--height", "1000")
        browser.command("wait", "--text", "outubro de 2025 — Cargos vagos: 93")
        assert browser.tooltip() == "outubro de 2025 — Cargos vagos: 93", browser.tooltip()
        browser.contained()
        browser.inspect(0, .92, "junho de 2025 — Cargos vagos: 79")


if __name__ == "__main__":
    main()
