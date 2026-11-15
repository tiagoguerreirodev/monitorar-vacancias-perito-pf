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
from tests.sources import CHECK_TIME, ControlledArchive, national_resources, resource_url, UnavailableUF
from tests.test_dashboard import monthly_resource
from tests.test_uf import ExportSource, NOW
from tests.test_uf_dashboard import RANKED


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
          // Native mouse coordinates are quantized; keep endpoints inside the plot.
          const x = {fraction} === 0 ? Math.ceil(screen.x)
            : {fraction} === 1 ? Math.floor(screen.x) : screen.x;
          return {{x, y: screen.y}};
        }})()""")

    def readout(self):
        return self.evaluate("""(() => {
          const value = document.querySelector('.inspection-value');
          return value && getComputedStyle(value).display !== 'none'
            ? value.textContent.trim() : null;
        })()""")

    def inspect(self, fraction, height, expected):
        point = self.point(fraction, height)
        self.move(point["x"], point["y"])
        observed = self.readout()
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
          const readout = document.querySelector('.inspection-readout');
          const box = readout.getBoundingClientRect();
          const clip = document.querySelector('.chart-scroll');
          const style = getComputedStyle(readout);
          return {left: box.left, right: box.right, top: box.top,
                  plotBottom: clip.getBoundingClientRect().bottom,
                  outside: !clip.contains(readout), label: readout.textContent,
                  position: style.position, selectable: style.userSelect !== 'none',
                  popup: !!document.querySelector('[role="tooltip"]'),
                  live: !!readout.closest('[aria-live], [role="status"], [role="alert"]'),
                  pageWidth: document.documentElement.scrollWidth, width: innerWidth,
                  fontSize: parseFloat(style.fontSize),
                  textFits: readout.scrollWidth <= readout.clientWidth};
        })()""")
        assert geometry["fontSize"] >= 16 and geometry["textFits"], geometry
        assert 0 <= geometry["left"] < geometry["right"] <= geometry["width"], geometry
        assert geometry["outside"] and geometry["top"] >= geometry["plotBottom"], geometry
        assert geometry["position"] == 'static' and geometry["selectable"], geometry
        assert 'Última inspeção:' in geometry["label"], geometry
        assert not geometry["popup"] and not geometry["live"], geometry
        assert geometry["pageWidth"] <= geometry["width"], geometry
        print("PASS labeled, selectable in-flow readout outside plot without overlap/overflow", geometry)

    def uf_geometry(self):
        """Read UF table geometry; each scenario keeps its own bounds policy."""
        return self.evaluate("""(() => {
          const table = document.querySelector('#uf-values');
          const region = table.closest('[role="region"]');
          const box = region.getBoundingClientRect();
          const rows = Array.from(table.tBodies[0].rows);
          const cells = rows.flatMap(row => Array.from(row.cells));
          const first = rows[0].getBoundingClientRect();
          return {rows: rows.map(row => [row.cells[0].textContent.split(' — ')[0],
                    Number(row.cells[1].textContent.replaceAll('.', ''))]),
            labels: rows.map(row => row.cells[0].textContent),
            cellBounds: cells.map(cell => cell.getBoundingClientRect().toJSON()),
            textBounds: cells.flatMap(cell => {
              const range = document.createRange(); range.selectNodeContents(cell);
              return Array.from(range.getClientRects()).map(rect => rect.toJSON());
            }), regionLeft: box.left, regionRight: box.right,
            firstTop: first.top, firstBottom: first.bottom, height: innerHeight,
            name: region.getAttribute('aria-label'), tabindex: region.tabIndex,
            headers: Array.from(table.tHead.rows[0].cells).map(cell => [cell.tagName, cell.scope]),
            display: getComputedStyle(table).display,
            regionWidth: region.clientWidth, regionContent: region.scrollWidth,
            pageWidth: document.documentElement.scrollWidth, width: innerWidth};
        })()""")

    def leave(self):
        last = self.readout()
        point = self.evaluate("""(() => {
          const readout = document.querySelector('.inspection-readout');
          readout.scrollIntoView({block: 'center'});
          const box = readout.getBoundingClientRect();
          return {x: (box.left + box.right) / 2, y: (box.top + box.bottom) / 2};
        })()""")
        self.move(point["x"], point["y"])
        assert last is not None and self.readout() == last, (last, self.readout())
        assert self.evaluate("getComputedStyle(document.querySelector('.inspection-guide')).display") == 'none'
        self.contained()
        print("PASS moving onto readout retains last month/value and hides guide without Escape")


def prepare(root):
    resources = {
        "national": national_resources(),
        "zero": {resource_url("2025-06"): monthly_resource("2025-06", 1195, 0)},
        "formatted": {
            resource_url("2025-06"): monthly_resource("2025-06", 50, 12345),
            resource_url("2025-08"): monthly_resource("2025-08", 1195, 0),
        },
        "allzero": {resource_url(month): monthly_resource(month, 0, 0)
                    for month in ("2025-06", "2025-08", "2025-09")},
        "single": {resource_url("2025-06"): monthly_resource("2025-06", 108, 12)},
        "sparse": {
            resource_url("2025-06"): monthly_resource("2025-06", 108, 12),
            resource_url("2025-09"): monthly_resource("2025-09", 120, 0),
            resource_url("2027-02"): monthly_resource("2027-02", 95, 25),
        },
    }
    for name, documents in resources.items():
        refresh_and_build(root / f"data-{name}",
                          root / f"www/{name}/monitorar-vacancias-perito-pf",
                          source=ControlledArchive(documents), uf_source=UnavailableUF(), clock=lambda: CHECK_TIME)
    refresh_and_build(root / 'data-uf', root / 'www/uf/monitorar-vacancias-perito-pf',
                      source=ControlledArchive(national_resources()), uf_source=ExportSource(), clock=lambda: NOW)
    fallback = root / "www/fallback/monitorar-vacancias-perito-pf"
    shutil.copytree(root / "www/national/monitorar-vacancias-perito-pf",
                    fallback, dirs_exist_ok=True)
    (fallback / "assets/inspection.js").unlink()  # Simulate an unavailable optional asset.
    print(root / "www")


def check_summary(browser):
    browser.setup()
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
        assert content['pageWidth'] <= width, content
        assert 'não representam vagas de concurso' in content['explanation'], content
        assert 'A data da verificação não é a referência dos cargos.' in content['explanation'], content
        assert 'data/history.json' in content['sources'] and 'data/status.json' in content['sources'], content
        assert ('https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/'
                'gestao-de-pessoas-executivo-federal-cargos-vagos') in content['sources'], content
    # Read the public local bytes, not application state; digest the external document.
    with urlopen(browser.url + 'data/history.json') as response:
        history = json.load(response)
    with urlopen(browser.url + 'data/status.json') as response:
        status = json.load(response)
    current = history['observations'][-1]
    source = 'https://repositorio.dados.gov.br/segrt/cargos%20vagos%20e%20vacancia/2026/CargosVagosVacancias_202609.ods'
    assert (current['reference_month'], current['occupied'], current['vacant'], current['authorized']) == (
        '2026-09', 1108, 87, 1195), current
    assert current['source']['url'] == source and source in content['sources'], current
    assert current['source']['sha256'] == sha256(national_resources()[source]).hexdigest(), current
    assert current['source']['retrieved_at'] == status['last_successful_check'] == '2026-11-13T12:00:00Z'
    print('PASS desktop/320px header, same-reference rate/context, vacancy axis/table, check vs reference and source bytes')


def check_single(browser):
    browser.setup()
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


def check_sparse(browser):
    browser.setup()
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


def check_narrow(browser):
    browser.setup(width=320, height=800)
    browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 79")
    browser.inspect(1 / 15 - .002, .92, "julho de 2025 — dados indisponíveis")
    browser.contained()
    # Keep the stationary pointer in the plot's visible area at both scroll ends.
    point = browser.point(0, .08)
    point['x'] = browser.evaluate("(() => { const r = document.querySelector('.chart-scroll').getBoundingClientRect(); return (r.left + r.right) / 2; })()")
    browser.move(point['x'], point['y'])
    assert browser.readout() == 'junho de 2025 — Cargos vagos: 79', browser.readout()
    browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
    browser.command("wait", "--text", "setembro de 2026 — Cargos vagos: 87")
    assert browser.readout() == "setembro de 2026 — Cargos vagos: 87", browser.readout()
    browser.inspect(1, .08, "setembro de 2026 — Cargos vagos: 87")
    browser.contained()
    # Move the plot near the bottom of the viewport through ordinary page scrolling.
    bottom = browser.point(1, .92)
    browser.evaluate(f"window.scrollBy(0, {bottom['y']} - (innerHeight - 12))")
    browser.inspect(1, .92, "setembro de 2026 — Cargos vagos: 87")
    browser.contained()
    browser.leave()


def check_fallback(browser):
    browser.setup()
    point = browser.point(3 / 15, .08)
    browser.move(point["x"], point["y"])
    assert browser.readout() is None, "No inspection-only placeholder without the optional script"
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
    assert browser.readout() is None, 'No enhancement should appear on mobile either'
    scroll = browser.evaluate("""(() => {
          const regions = Array.from(document.querySelectorAll('[role="region"]'));
          regions.forEach(region => { region.scrollLeft = 99999; });
          return {offsets: regions.map(region => region.scrollLeft),
                  names: regions.map(region => region.getAttribute('aria-label')),
                  pageWidth: document.documentElement.scrollWidth, pageX: scrollX};
        })()""")
    assert all(offset > 0 for offset in scroll['offsets']), scroll
    assert all(scroll['names']) and scroll['pageWidth'] <= 320 and scroll['pageX'] == 0, scroll
    print("PASS unavailable JS leaves useful static chart, equivalent table and named tab stops; independent 320px scrollers", scroll)


def check_allzero(browser):
    browser.setup()
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


def check_formatted(browser):
    browser.setup()
    browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 12.345")
    browser.inspect(.5, .92, "julho de 2025 — dados indisponíveis")
    browser.inspect(1, .08, "agosto de 2025 — Cargos vagos: 0")
    browser.contained()
    browser.command("viewport", "--width", "1000", "--height", "1000")
    browser.inspect(.5, .08, "julho de 2025 — dados indisponíveis")
    browser.inspect(0, .92, "junho de 2025 — Cargos vagos: 12.345")
    browser.contained()
    browser.leave()


def check_zero(browser):
    browser.setup()
    for fraction, height in ((0, .08), (.5, .92), (1, .08)):
        browser.inspect(fraction, height, "junho de 2025 — Cargos vagos: 0")
        browser.contained()
    browser.leave()


def check_prose(browser):
    browser.command('viewport', '--width', '1440', '--height', '1000')
    paragraphs = browser.evaluate("""(() => {
      return Array.from(document.querySelectorAll('p')).filter(p => p.checkVisibility()).map(paragraph => {
        const lines = [];
        const walker = document.createTreeWalker(paragraph, NodeFilter.SHOW_TEXT);
        const tolerance = parseFloat(getComputedStyle(paragraph).fontSize) / 2;
        while (walker.nextNode()) {
          const node = walker.currentNode;
          for (let i = 0; i < node.length; i++) {
            const range = document.createRange();
            range.setStart(node, i); range.setEnd(node, i + 1);
            const box = range.getBoundingClientRect();
            if (!box.width || !box.height) continue;
            let line = lines.find(line => Math.abs(line.top - box.top) < tolerance);
            if (!line) { line = {top: box.top, text: ''}; lines.push(line); }
            line.text += node.textContent[i];
          }
        }
        return {text: paragraph.textContent.trim(),
          lines: lines.map(line => line.text.trim().length),
          font: getComputedStyle(paragraph).fontFamily,
          width: paragraph.getBoundingClientRect().width};
      }).filter(paragraph => paragraph.lines.length);
    })()""")
    full_lines = [length for paragraph in paragraphs for length in paragraph['lines'][:-1]]
    assert full_lines and max(length for paragraph in paragraphs for length in paragraph['lines']) <= 75, paragraphs
    assert max(full_lines) >= 60, paragraphs
    data = browser.evaluate("""({chart: document.querySelector('.chart-scroll').clientWidth,
      table: document.querySelector('.uf-table').clientWidth,
      panel: document.querySelector('#uf-panel').clientWidth})""")
    assert data['chart'] > 1000 and data['table'] > 1000, data
    for width in (320, 720):
        browser.command('viewport', '--width', str(width), '--height', '1000')
        assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert browser.evaluate("Array.from(document.querySelectorAll('p')).every(p => p.scrollWidth <= p.clientWidth + 1)")
    print('PASS measured desktop prose lines, full-width data, 320/720px normal wrapping', paragraphs, data)


def check_skip(browser):
    browser.command('viewport', '--width', '1440', '--height', '1000')
    browser.evaluate('window.scrollTo(0, 0)')
    # A real click at the page origin focuses an otherwise background Orca page.
    browser.move(1, 1)
    browser.command('mouse', 'down')
    browser.command('mouse', 'up')
    browser.command('reload')  # Start the first Tab in a fresh document, not a restored tab position.
    browser.command('viewport', '--width', '1440', '--height', '1000')
    browser.command('keypress', '--key', 'Tab')
    focus = browser.evaluate("""(() => {
      const link = document.querySelector('.skip-link');
      const box = link.getBoundingClientRect();
      let adjacent = document.elementFromPoint(box.right + 5, (box.top + box.bottom) / 2);
      while (adjacent && getComputedStyle(adjacent).backgroundColor === 'rgba(0, 0, 0, 0)')
        adjacent = adjacent.parentElement;
      const luminance = color => {
        const rgb = color.match(/[0-9.]+/g).slice(0, 3).map(Number).map(n => n / 255)
          .map(n => n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4);
        return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2];
      };
      const style = getComputedStyle(link);
      const background = getComputedStyle(adjacent).backgroundColor;
      const a = luminance(style.outlineColor), b = luminance(background);
      return {first: document.activeElement === link, visible: box.top >= 0,
        outline: style.outlineColor, background, outlineWidth: style.outlineWidth,
        contrast: (Math.max(a, b) + .05) / (Math.min(a, b) + .05)};
    })()""")
    assert focus['first'] and focus['visible'] and float(focus['outlineWidth'][:-2]) > 0, focus
    assert focus['outline'] == 'rgb(255, 255, 255)' and focus['contrast'] >= 3, focus
    browser.command('keypress', '--key', 'Enter')
    browser.url = browser.url.split('#')[0] + '#conteudo'
    target = browser.evaluate("({id: document.activeElement.id, tag: document.activeElement.tagName})")
    assert target == {'id': 'conteudo', 'tag': 'MAIN'}, target
    print('PASS first native Tab reveals local contrasting skip focus; Enter focuses main', focus, target)


def check_uf_layout(browser):
    browser.command('viewport', '--width', '320', '--height', '1000')
    browser.evaluate("document.querySelector('#uf-values').scrollIntoView({block:'start'})")
    content = browser.uf_geometry()
    content['cellsFit'] = all(rect['left'] >= content['regionLeft'] and
                              rect['right'] <= content['regionRight'] + 1
                              for rect in content['cellBounds'])
    content['firstVisible'] = content['firstBottom'] < content['height']
    content.update(browser.evaluate("""({
      chartScrolls: document.querySelector('.chart-scroll').scrollWidth >
                    document.querySelector('.chart-scroll').clientWidth,
      nationalScrolls: document.querySelector('#history-values').scrollWidth >
                       document.querySelector('#history-values').parentElement.clientWidth
    })"""))
    assert content['rows'] == [list(row) for row in RANKED], content
    assert content['labels'][0] == 'DF — Distrito Federal', content
    assert 'RN — Rio Grande do Norte' in content['labels'], content
    assert content['cellsFit'] and content['firstVisible'], content
    assert content['regionContent'] <= content['regionWidth'], content
    assert content['pageWidth'] <= content['width'] == 320, content
    assert content['display'] == 'table' and content['headers'] == [['TH', 'col'], ['TH', 'col']], content
    assert content['name'] and content['tabindex'] == 0, content
    assert content['chartScrolls'] and content['nationalScrolls'], content
    print('PASS 320px UF first rows/both columns, full 27 exact counts/native headers; national scrollers retained', content)


def check_initial(browser):
    browser.setup()
    assert browser.readout() == ('Mova o ponteiro sobre o gráfico para inspecionar um mês, '
                                 'ou consulte a tabela abaixo.'), browser.readout()
    browser.contained()
    assert browser.evaluate("getComputedStyle(document.querySelector('.inspection-guide')).display") == 'none'
    print('PASS initial pointer/table instruction without an invented month/value')


def check_nearest(browser):
    browser.setup()
    # September 2025 is slot 3 of 16, away from every marker/line vertically.
    browser.inspect(3 / 15, .08, "setembro de 2025 — Cargos vagos: 87")


def check_gap(browser):
    check_nearest(browser)
    browser.inspect(1 / 15, .08, "julho de 2025 — dados indisponíveis")
    browser.inspect(1 / 15, .92, "julho de 2025 — dados indisponíveis")
    browser.guide(1 / 15)
    browser.inspect(2 / 15, .92, "agosto de 2025 — Cargos vagos: 84")


def check_leave(browser):
    check_nearest(browser)
    browser.leave()


def check_clamp(browser):
    check_nearest(browser)
    browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
    browser.inspect(1, .92, "setembro de 2026 — Cargos vagos: 87")
    browser.contained()


def check_scroll(browser):
    check_nearest(browser)
    browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 341.333333")
    browser.command("wait", "--text", "janeiro de 2026 — Cargos vagos: 101")
    assert browser.readout() == "janeiro de 2026 — Cargos vagos: 101", browser.readout()
    browser.contained()
    browser.inspect(14 / 15, .08, "agosto de 2026 — Cargos vagos: 128")


def check_edges(browser):
    check_nearest(browser)
    browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 79")
    browser.inspect(7.5 / 15 - .001, .92, "janeiro de 2026 — Cargos vagos: 101")
    browser.inspect(7.5 / 15, .08, "fevereiro de 2026 — Cargos vagos: 105")
    browser.inspect(7.5 / 15 + .001, .92, "fevereiro de 2026 — Cargos vagos: 105")
    browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
    browser.inspect(1, .08, "setembro de 2026 — Cargos vagos: 87")
    browser.leave()


def check_resize(browser):
    check_nearest(browser)
    browser.command("viewport", "--width", "1200", "--height", "1000")
    browser.command("wait", "--text", "outubro de 2025 — Cargos vagos: 93")
    assert browser.readout() == "outubro de 2025 — Cargos vagos: 93", browser.readout()
    browser.contained()
    browser.inspect(0, .92, "junho de 2025 — Cargos vagos: 79")


# Every selectable case names both its documents and its complete check.
CASES = {
    "prose": ("uf", check_prose),
    "skip": ("national", check_skip),
    "uf-layout": ("uf", check_uf_layout),
    "initial": ("national", check_initial),
    "nearest": ("national", check_nearest),
    "gap": ("national", check_gap),
    "leave": ("national", check_leave),
    "clamp": ("national", check_clamp),
    "scroll": ("national", check_scroll),
    "resize": ("national", check_resize),
    "edges": ("national", check_edges),
    "zero": ("zero", check_zero),
    "narrow": ("national", check_narrow),
    "formatted": ("formatted", check_formatted),
    "fallback": ("fallback", check_fallback),
    "allzero": ("allzero", check_allzero),
    "summary": ("national", check_summary),
    "single": ("single", check_single),
    "sparse": ("sparse", check_sparse),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("--root", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--orca", required=True, help="Executable resolved by the Orca skill")
    check.add_argument("--page", required=True, help="Your explicitly owned browser page ID")
    check.add_argument("--base-url", required=True, help="Local preview root, ending in /")
    check.add_argument("--case", choices=CASES, default="nearest")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.root)
        return
    assert urlsplit(args.base_url).hostname in {"127.0.0.1", "localhost"}, "Local preview only"
    assert args.page != "fff658ce-af08-4721-b944-f11fa526a5c0", "Protected user page"
    fixture, run_check = CASES[args.case]
    url = args.base_url.rstrip("/") + f"/{fixture}/monitorar-vacancias-perito-pf/"
    run_check(Browser(args.orca, args.page, url))


if __name__ == "__main__":
    main()
