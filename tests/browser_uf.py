"""Optional owned-Orca UF acceptance; controlled complete builds, no government I/O.

Run prepare, serve ROOT/www locally, create your own page, then run check.
Screenshots are URL-guarded before/after and followed by an explicit viewport
reset before actual mouse movement (Orca screenshots may change viewport state).
DOM evaluation only reads/measures or scrolls. No synthetic input or app helpers.
"""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit
from urllib.request import urlopen

from perito_dashboard import refresh_and_build
from tests import browser_mouse as national
from tests.sources import ControlledArchive, UnavailableUF, national_resources
from tests.test_uf import ExportSource, NOW, UnavailableNational
from tests.test_uf_dashboard import RANKED
from tests.test_uf_history import counterfactual

PROTECTED = 'fff658ce-af08-4721-b944-f11fa526a5c0'
# Independent full labels, in the literal RANKED order, not renderer-derived.
LABELS = ['DF — Distrito Federal', 'SP — São Paulo', 'MG — Minas Gerais',
          'PR — Paraná', 'RS — Rio Grande do Sul', 'RJ — Rio de Janeiro',
          'SC — Santa Catarina', 'PE — Pernambuco', 'CE — Ceará', 'GO — Goiás',
          'BA — Bahia', 'MS — Mato Grosso do Sul', 'PB — Paraíba', 'RO — Rondônia',
          'ES — Espírito Santo', 'RN — Rio Grande do Norte', 'AL — Alagoas',
          'AM — Amazonas', 'PI — Piauí', 'MT — Mato Grosso', 'PA — Pará',
          'SE — Sergipe', 'TO — Tocantins', 'MA — Maranhão', 'AC — Acre',
          'RR — Roraima', 'AP — Amapá']


class OwnedBrowser(national.Browser):
    def __init__(self, executable, page, url, evidence):
        assert page != PROTECTED
        super().__init__(executable, page, url)
        self.evidence = evidence
        evidence.mkdir(parents=True, exist_ok=True)
        self.width, self.height = 1440, 1000
        self.needs_capture = True
        self.sequence = 0

    def command(self, *args):
        result = super().command(*args)
        if args[0] == 'viewport':
            self.width = int(args[args.index('--width') + 1])
            self.height = int(args[args.index('--height') + 1])
            self.needs_capture = True
        return result

    def capture(self, label):
        assert self.evaluate('location.href') == self.url
        completed = subprocess.run([self.executable, 'screenshot', '--page', self.page, '--json'],
                                   text=True, capture_output=True, check=True)
        receipt = json.loads(completed.stdout)
        assert receipt.get('ok'), receipt
        assert self.evaluate('location.href') == self.url
        self.sequence += 1
        path = self.evidence / f'{self.sequence:03d}-{label}-{self.width}.png'
        image = receipt['result']['path'].replace('\\', '/')
        if image[1:3] == ':/' and Path('/mnt').is_dir():
            image = '/mnt/' + image[0].lower() + image[2:]
        shutil.copyfile(image, path)
        # Screenshot can reset emulation. Reset AFTER the screenshot, before input.
        super().command('viewport', '--width', str(self.width), '--height', str(self.height))
        self.needs_capture = False
        print('PNG', path, flush=True)

    def move(self, x, y):
        if self.needs_capture:
            self.capture('before-mouse')
        return super().move(x, y)

    def navigate(self, url):
        self.command('goto', '--url', url)
        self.url = url
        # Each navigation resets emulation; do not inherit the previous page state.
        self.command('viewport', '--width', str(self.width), '--height', str(self.height))


def prepare(root):
    national.prepare(root)
    for name, source in [('uf', ControlledArchive(national_resources())),
                         ('only-uf', UnavailableNational()), ('no-uf', ControlledArchive(national_resources()))]:
        refresh_and_build(root / f'data-{name}', root / f'www/{name}/monitorar-vacancias-perito-pf',
                          source=source, uf_source=UnavailableUF() if name == 'no-uf' else ExportSource(),
                          clock=lambda: NOW)
    # Equal semantic aggregates, independently regenerated source bytes/receipt.
    refresh_and_build(root / 'data-uf', root / 'www/uf/monitorar-vacancias-perito-pf',
                      source=UnavailableNational(), uf_source=ExportSource(run=7),
                      clock=lambda: NOW + timedelta(days=1))
    # COUNTERFACTUAL November observation, then a failed UF check. This is
    # prospective archive/retention coverage, not a new official observation.
    archive_site = root / 'www/uf-archive/monitorar-vacancias-perito-pf'
    for day, source in ((0, ExportSource()), (1, counterfactual('2026-11')), (2, UnavailableUF())):
        refresh_and_build(root / 'data-uf-archive', archive_site,
                          source=ControlledArchive(national_resources()), uf_source=source,
                          clock=lambda: NOW + timedelta(days=day))
    target = root / 'www/uf-fallback/monitorar-vacancias-perito-pf'
    shutil.copytree(root / 'www/uf/monitorar-vacancias-perito-pf', target, dirs_exist_ok=True)
    (target / 'assets/inspection.js').unlink()


def check_uf(browser, only_uf=False):
    for width in (1440, 320):
        browser.command('viewport', '--width', str(width), '--height', '1000')
        browser.evaluate("document.querySelector('#uf-panel').scrollIntoView({block:'start'})")
        content = browser.evaluate("""(() => {
          const panel = document.querySelector('#uf-panel');
          const bars = document.querySelector('#uf-bars');
          const region = document.querySelector('.uf-table');
          return {text: panel.textContent, reference: document.querySelector('#uf-reference').dateTime,
            checked: document.querySelector('#uf-check').dateTime,
            retrieved: document.querySelector('#uf-retrieved').dateTime,
            rows: Array.from(document.querySelector('#uf-values').tBodies[0].rows)
              .map(row => [row.cells[0].textContent.split(' — ')[0], Number(row.cells[1].textContent.replaceAll('.', ''))]),
            labels: Array.from(bars.children).map(row => row.textContent),
            bars: Array.from(bars.querySelectorAll('.uf-track > span')).map(bar => bar.getBoundingClientRect().width),
            name: region.getAttribute('aria-label'), tabindex: region.tabIndex,
            width: innerWidth, pageWidth: document.documentElement.scrollWidth,
            count: document.querySelector('#vacant-count')?.textContent ?? null};
        })()""")
        assert content['rows'] == [list(row) for row in RANKED], content
        assert len(content['labels']) == 27 and 'DF — Distrito Federal' in content['labels'][0], content
        for label, (uf, count) in zip(content['labels'], RANKED):
            assert label.startswith(uf + ' — ') and f'{count} pessoas ativas' in label, label
        assert content['bars'] == sorted(content['bars'], reverse=True), content
        assert content['pageWidth'] <= content['width'] == width, content
        assert content['reference'] == '2026-09', content
        assert content['checked'] == ('2026-11-14T12:00:00Z' if only_uf else '2026-11-15T12:00:00Z'), content
        assert content['retrieved'] == ('2026-11-14T05:55:38.701Z' if only_uf else '2026-11-14T05:56:04.896Z'), content
        assert 'premissa do projeto' in content['text'] and 'não verificada oficialmente' in content['text'], content
        assert content['count'] == (None if only_uf else '87'), content
        coverage = browser.evaluate("document.querySelector('#uf-coverage').textContent")
        for phrase in ('1 mês aceito', 'setembro de 2026 a setembro de 2026',
                       'Sem lacunas', 'Uma única observação', 'Não há consulta retrospectiva'):
            assert phrase in coverage, (phrase, coverage)
        assert 'mês(es)' not in coverage and 'aceito(s)' not in coverage, coverage
        assert content['name'] == 'Tabela de pessoal ativo por UF' and content['tabindex'] == 0, content
        browser.capture('uf-assumption')
        browser.evaluate("document.querySelector('#uf-bars li').scrollIntoView({block:'center'})")
        browser.capture('uf-ranked')
        point = browser.evaluate("""(() => {const r = document.querySelector('#uf-bars li').getBoundingClientRect();
          return {x: (r.left+r.right)/2, y: (r.top+r.bottom)/2};})()""")
        browser.move(point['x'], point['y'])
        browser.evaluate("document.querySelector('#uf-values').scrollIntoView({block:'start'}); document.querySelector('.uf-table').scrollLeft=0")
        geometry = browser.uf_geometry()
        geometry['cellsFit'] = all(rect['left'] >= geometry['regionLeft'] and
                                   rect['right'] <= geometry['regionRight']
                                   for rect in geometry['textBounds'])
        geometry['firstVisible'] = (geometry['firstTop'] >= 0 and
                                    geometry['firstBottom'] <= geometry['height'])
        assert geometry['cellsFit'] and geometry['firstVisible'], geometry
        assert geometry['labels'] == LABELS, geometry
        assert geometry['display'] == 'table' and geometry['headers'] == [['TH', 'col'], ['TH', 'col']], geometry
        assert geometry['regionContent'] <= geometry['regionWidth'] and geometry['pageWidth'] <= width, geometry
        browser.capture('uf-first-rows-both-columns')
        browser.evaluate("document.querySelector('.uf-table').scrollLeft=99999")
        assert browser.evaluate("document.querySelector('.uf-table').scrollLeft") == 0
        browser.evaluate("document.querySelector('#uf-values').tBodies[0].lastElementChild.scrollIntoView({block:'center'})")
        browser.capture('uf-last-rows-both-columns')
        browser.evaluate("document.querySelector('.uf-provenance').scrollIntoView({block:'center'})")
        browser.capture('uf-source')
        print('PASS UF', width, 'exact 27 counts, bars, independent dates, scope, premise; both table columns fit without horizontal scroll', geometry, flush=True)
    with urlopen(browser.url + 'data/uf.json') as response:
        saved = json.load(response)
    assert saved['current']['counts_by_uf'] == dict(RANKED)
    assert saved['current']['total'] == 1108
    with urlopen(browser.url + 'data/uf-status.json') as response:
        status = json.load(response)
    assert status['last_export']['source']['sha256'] == (
        '5f88f93738b41b035a4bf58450292366afd2aa28b66019c8103e079c0aa6fb55' if only_uf else
        'fbffe323c3485bed0024afe6133f450dc20f51ab8c7aba65a1079be6476e345c')
    if not only_uf:
        assert browser.evaluate("document.querySelector('.context time').dateTime") == '2026-11-14T12:00:00Z'
        check_links(browser)
        # Exercise the public inspection lifecycle on the COMPOSED artifact too.
        national.check_initial(browser)
        browser.capture('composed-initial')
        national.check_gap(browser)
        browser.capture('composed-mouse-desktop')
        national.check_leave(browser)
        browser.capture('composed-retained-readout')
        national.check_scroll(browser)
        national.check_resize(browser)
        national.check_narrow(browser)
        browser.inspect(1, .08, 'setembro de 2026 — Cargos vagos: 87')
        browser.capture('composed-mouse-320')


def check_unavailable(browser, national_missing=False):
    for width in (1440, 320):
        browser.command('viewport', '--width', str(width), '--height', '1000')
        text = browser.evaluate('document.body.textContent')
        if national_missing:
            for wording in ('Dados nacionais indisponíveis',
                            'Nenhuma observação nacional válida está disponível.',
                            'Verificação nacional indisponível.',
                            'Recorte do histórico nacional:',
                            'Fonte nacional indisponível; nenhum retrato nacional aceito.'):
                assert wording in text, (wording, text)
            assert browser.evaluate("document.querySelector('#vacant-count') === null && document.querySelector('#history-chart') === null")
            assert browser.readout() is None
            assert browser.evaluate("document.querySelector('#uf-values').tBodies[0].rows.length") == 27
            browser.evaluate("document.querySelector('.panel').scrollIntoView({block:'start'})")
        else:
            assert 'Pessoal ativo por UF indisponível — sem observação aceita; ausência não é zero.' in text, text
            assert browser.evaluate("document.querySelector('#uf-bars') === null && document.querySelector('#uf-values') === null")
            assert browser.evaluate("document.querySelector('#vacant-count').textContent === '87'")
            assert browser.evaluate("document.querySelector('#history-values').tBodies[0].rows.length") == 16
            browser.evaluate("Array.from(document.querySelectorAll('.panel')).at(-1).scrollIntoView({block:'center'})")
        assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth')
        browser.capture('national-unavailable' if national_missing else 'uf-unavailable')
    links = browser.evaluate("Array.from(document.querySelectorAll('main a')).map(a => a.getAttribute('href'))")
    for link in ('data/history.json', 'data/status.json'):
        assert (link in links) == (not national_missing), links
    if not national_missing:
        with urlopen(browser.url + 'data/status.json') as response:
            assert json.load(response)['last_successful_check'] == '2026-11-14T12:00:00Z'
    print('PASS independent first absence, explicit unavailable is not zero, healthy feed usable', national_missing, flush=True)


def check_archive(browser):
    for width in (1440, 320):
        browser.command('viewport', '--width', str(width), '--height', '1000')
        browser.evaluate("document.querySelector('#uf-coverage').scrollIntoView({block:'center'})")
        text = browser.evaluate("document.querySelector('#uf-coverage').textContent")
        for phrase in ('2 meses aceitos', 'setembro de 2026 a novembro de 2026',
                       'outubro de 2026', 'Não há consulta retrospectiva'):
            assert phrase in text, (phrase, text)
        assert 'mês(es)' not in text and 'aceito(s)' not in text, text
        assert browser.evaluate("document.querySelector('#uf-reference').dateTime") == '2026-11'
        assert browser.evaluate("document.querySelector('#uf-check').dateTime") == '2026-11-15T12:00:00Z'
        assert browser.evaluate("document.querySelector('.context time').dateTime") == '2026-11-16T12:00:00Z'
        assert browser.evaluate("document.querySelector('#vacant-count').textContent === '87'")
        assert browser.evaluate("document.querySelector('#uf-values').tBodies[0].rows.length") == 27
        assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth')
        browser.capture('counterfactual-plural-coverage-retained-uf')
    with urlopen(browser.url + 'data/uf-history.json') as response:
        archive = json.load(response)
    assert archive['coverage'] == {'available_months': ['2026-09', '2026-11'],
        'start': '2026-09', 'end': '2026-11', 'missing_months': ['2026-10']}, archive
    assert all(row['counts_by_uf'] == dict(RANKED) for row in archive['observations']), archive
    check_links(browser)
    print('PASS counterfactual plural/gap/prospective coverage; failed UF retains accepted counts/check independently', flush=True)


def check_fallback(browser):
    for width in (1440, 320):
        browser.setup(width=width)
        point = browser.point(0, .08)
        browser.move(point['x'], point['y'])
        assert browser.readout() is None
        assert browser.evaluate("!document.querySelector('.inspection-readout')?.checkVisibility()")
        assert browser.evaluate("document.querySelector('#history-chart').checkVisibility()")
        assert browser.evaluate("document.querySelectorAll('#uf-bars li').length") == 27
        assert browser.evaluate("document.querySelector('#uf-values').tBodies[0].rows.length") == 27
        assert browser.evaluate("document.querySelector('#history-values').tBodies[0].rows.length") == 16
        assert browser.evaluate('document.documentElement.scrollWidth <= innerWidth')
        browser.capture('composed-static-fallback')
        browser.evaluate("document.querySelector('#uf-values').scrollIntoView({block:'start'})")
        browser.capture('fallback-uf-table')
    check_links(browser)
    print('PASS composed unavailable-JS asset: no empty readout; complete SVG, tables and source/JSON links', flush=True)


def check_links(browser):
    links = browser.evaluate("Array.from(document.querySelectorAll('main a')).map(a => a.getAttribute('href'))")
    for name in ('history', 'status', 'uf', 'uf-status'):
        assert f'data/{name}.json' in links, links
        with urlopen(browser.url.split('#')[0] + f'data/{name}.json') as response:
            assert json.load(response)['schema_version'] == 1
    assert any('CargosVagosVacancias_202609.ods' in link for link in links), links
    assert any('pep' in link.lower() for link in links), links


def check_keyboard(browser):
    # Native Tab/Enter only: the real skip-link test also measures local contrast.
    national.check_skip(browser)
    browser.capture('skip-destination')
    check_links(browser)
    for _ in range(60):
        browser.command('keypress', '--key', 'Tab')
        active = browser.evaluate("document.activeElement.getAttribute('href')")
        if active == 'data/uf-status.json':
            break
    else:
        raise AssertionError('UF provenance JSON not reachable by native Tab')
    browser.capture('keyboard-uf-provenance')
    destination = browser.url.split('#')[0] + active
    browser.command('keypress', '--key', 'Enter')
    browser.url = destination
    assert browser.evaluate('location.href') == destination
    browser.capture('keyboard-opened-uf-json')
    print('PASS native keyboard reaches and opens real local UF provenance JSON', destination, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'check'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--orca', default='orca')
    parser.add_argument('--page')
    parser.add_argument('--base-url', default='http://127.0.0.1:8144/')
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.root)
        return
    assert args.page and args.page != PROTECTED
    assert urlsplit(args.base_url).hostname in {'127.0.0.1', 'localhost'}
    def url(name):
        return args.base_url.rstrip('/') + f'/{name}/monitorar-vacancias-perito-pf/'
    browser = OwnedBrowser(args.orca, args.page, url('national'), args.root / 'evidence')
    # Caller creates a fresh page at this exact URL.
    assert browser.evaluate('location.href') == browser.url
    # Keep every national assertion, including the exact tie. Report failures only
    # after the remaining composed cases run; a native limitation is NOT a pass.
    checks = [(case, fixture, run_check) for case, (fixture, run_check) in national.CASES.items()]
    checks.extend([
        ('composed', 'uf', check_uf),
        ('only-uf', 'only-uf', lambda b: (check_uf(b, only_uf=True), check_unavailable(b, national_missing=True))),
        ('no-uf', 'no-uf', check_unavailable),
        ('composed-archive', 'uf-archive', check_archive),
        ('composed-fallback', 'uf-fallback', check_fallback),
        ('composed-keyboard', 'uf', check_keyboard),
    ])
    failures = []
    for case, fixture, run_check in checks:
        browser.navigate(url(fixture))
        try:
            run_check(browser)
        except AssertionError as error:
            failures.append(case)
            print('FAIL', case, repr(error), flush=True)
        else:
            print('PASS case', case, flush=True)
    assert not failures, failures


if __name__ == '__main__':
    main()
