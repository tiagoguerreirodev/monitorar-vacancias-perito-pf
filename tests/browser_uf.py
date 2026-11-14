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

PROTECTED = 'fff658ce-af08-4721-b944-f11fa526a5c0'


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
        shutil.copyfile(receipt['result']['path'], path)
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
        assert content['pageWidth'] == content['width'] == width, content
        assert content['reference'] == '2026-09', content
        assert content['checked'] == ('2026-11-14T12:00:00Z' if only_uf else '2026-11-15T12:00:00Z'), content
        assert content['retrieved'] == ('2026-11-14T05:55:38.701Z' if only_uf else '2026-11-14T05:56:04.896Z'), content
        assert 'premissa do projeto' in content['text'] and 'não verificada oficialmente' in content['text'], content
        assert content['count'] == (None if only_uf else '87'), content
        assert content['name'] and content['tabindex'] == 0, content
        browser.capture('uf-assumption')
        browser.evaluate("document.querySelector('#uf-bars li').scrollIntoView({block:'center'})")
        browser.capture('uf-ranked')
        point = browser.evaluate("""(() => {const r = document.querySelector('#uf-bars li').getBoundingClientRect();
          return {x: (r.left+r.right)/2, y: (r.top+r.bottom)/2};})()""")
        browser.move(point['x'], point['y'])
        browser.evaluate("document.querySelector('.uf-table').scrollIntoView({block:'center'}); document.querySelector('.uf-table').scrollLeft=0")
        browser.capture('uf-exact-table')
        browser.evaluate("document.querySelector('.uf-table').scrollLeft=99999")
        geometry = browser.evaluate("({offset: document.querySelector('.uf-table').scrollLeft, width: document.documentElement.scrollWidth})")
        assert geometry['width'] == width and (width != 320 or geometry['offset'] > 0), geometry
        browser.capture('uf-table-scrolled')
        browser.evaluate("document.querySelector('.uf-provenance').scrollIntoView({block:'center'})")
        browser.capture('uf-source')
        print('PASS UF', width, 'exact 27 counts, bars, dates, scope, premise, source and contained scroll', flush=True)
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
        # Exercise the national public mouse contract on the COMPOSED artifact too.
        national.check_gap(browser)
        browser.capture('composed-mouse-desktop')
        national.check_narrow(browser)
        browser.inspect(1, .08, 'setembro de 2026 — Cargos vagos: 87')
        browser.capture('composed-mouse-320')


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
    for case, (fixture, run_check) in national.CASES.items():
        browser.navigate(url(fixture))
        run_check(browser)
        print('PASS national case', case, flush=True)
    browser.navigate(url('uf'))
    check_uf(browser)
    browser.navigate(url('only-uf'))
    check_uf(browser, only_uf=True)
    browser.navigate(url('no-uf'))
    assert browser.evaluate("document.querySelector('#uf-bars') === null")
    assert 'ausência não é zero' in browser.evaluate('document.body.textContent')
    browser.evaluate("Array.from(document.querySelectorAll('.panel')).at(-1).scrollIntoView({block:'center'})")
    browser.capture('uf-unavailable')
    browser.navigate(url('uf-fallback'))
    for width in (1440, 320):
        browser.setup(width=width)
        point = browser.point(0, .08)
        browser.move(point['x'], point['y'])
        assert browser.tooltip() is None
        assert browser.evaluate("document.querySelectorAll('#uf-bars li').length") == 27
        assert browser.evaluate("document.querySelector('#uf-values').tBodies[0].rows.length") == 27
        assert browser.evaluate("document.querySelector('#history-values').tBodies[0].rows.length") == 16
        browser.capture('composed-static-fallback')
    print('PASS composed static fallback and both first-absence directions', flush=True)


if __name__ == '__main__':
    main()
