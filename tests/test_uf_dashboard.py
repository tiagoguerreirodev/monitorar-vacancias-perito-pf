"""UF presentation through both controlled sources and the public complete build."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

from perito_dashboard import refresh_and_build
from tests.sources import ControlledArchive, UnavailableUF, national_resources, monthly_resource, SEPTEMBER_URL
from tests.test_dashboard import Page, monthly_resource as national_counts
from tests.test_uf import ExportSource, NOW, UnavailableNational, workbook_variant

# Independent literal expectations from the two documented genuine exports.
RANKED = [('DF', 324), ('SP', 130), ('MG', 79), ('PR', 71), ('RS', 57),
          ('RJ', 55), ('SC', 37), ('PE', 31), ('CE', 30), ('GO', 28),
          ('BA', 27), ('MS', 27), ('PB', 25), ('RO', 24), ('ES', 21),
          ('RN', 15), ('AL', 14), ('AM', 14), ('PI', 14), ('MT', 13),
          ('PA', 13), ('SE', 12), ('TO', 12), ('MA', 11), ('AC', 9),
          ('RR', 8), ('AP', 7)]


class UFDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.site = self.root / 'data', self.root / 'site'

    def refresh(self, national=None, uf=None, day=0):
        refresh_and_build(self.data, self.site,
                          source=national if national is not None else ControlledArchive(national_resources()),
                          uf_source=uf if uf is not None else ExportSource(),
                          clock=lambda: NOW + timedelta(days=day))
        return Page((self.site / 'index.html').read_text())

    def counts(self, page):
        table = page.one('table', id='uf-values')
        rows = [n for n in page.matching('tr') if table in n['parents']][1:]
        return [(next(n['text'] for n in page.matching('th') if row in n['parents']).split(' — ')[0],
                 int(next(n['text'] for n in page.matching('td') if row in n['parents']).replace('.', '')))
                for row in rows]

    def test_genuine_27_ufs_are_ranked_with_exact_counts_and_explicit_personnel_scope(self):
        page = self.refresh()
        self.assertEqual(self.counts(page), RANKED)
        bars = page.one('ol', id='uf-bars')
        self.assertEqual(bars['attrs'].get('role'), 'list')
        items = [n for n in page.matching('li') if bars in n['parents']]
        self.assertEqual(len(items), 27)
        for item, (uf, count) in zip(items, RANKED):
            self.assertTrue(item['text'].startswith(uf + ' — '))
            self.assertIn(str(count), item['text'])
        self.assertIn('DF — Distrito Federal', bars['text'])
        self.assertIn('Total: 1.108 PCFs ativos', page.text(id='uf-panel'))
        self.assertIn('27 UFs, incluindo o Distrito Federal', page.text(id='uf-panel'))
        self.assertIn('premissa do projeto', page.text(id='uf-assumption'))
        self.assertIn('não verificada oficialmente', page.text(id='uf-assumption'))
        self.assertIn('UF Servidores', page.text(id='uf-assumption'))
        self.assertIn('Pessoas ativas não são cargos ocupados', page.text(id='uf-panel'))
        self.assertIn('sem série histórica UF', page.text(id='uf-panel'))
        self.assertEqual(page.text(id='uf-reference'), 'setembro de 2026')
        self.assertEqual(page.text(id='uf-check'), '14/11/2026 às 09:00 (Brasília, UTC−03:00)')
        self.assertEqual(page.text(id='uf-retrieved'), '14/11/2026 às 02:55 (Brasília, UTC−03:00)')
        self.assertTrue(page.matching('a', href='https://pep.paineis.gov.br/extensions/pep/index.html'))
        for link in ('data/uf.json', 'data/uf-status.json'):
            self.assertTrue(page.matching('a', href=link))
            self.assertEqual((self.site / link).read_bytes(), (self.data / Path(link).name).read_bytes())
        self.assertIn('5f88f93738b41b035a4bf58450292366afd2aa28b66019c8103e079c0aa6fb55', page.text(id='uf-panel'))
        region = page.one('div', **{'aria-label': 'Tabela de pessoal ativo por UF; role horizontalmente em telas pequenas'})
        self.assertEqual(region['attrs']['tabindex'], '0')
        self.assertEqual(page.text(id='vacant-count'), '87')
        self.assertEqual(page.text(id='vacancy-rate'), '7,3%')
        self.assertIn('julho de 2025: indisponível', page.text(id='history-chart'))
        current = json.loads((self.data / 'uf.json').read_text())['current']
        self.assertEqual(current['total'], 1108)
        self.assertEqual(current['counts_by_uf'], dict(RANKED))

    def test_reexport_uses_latest_receipt_not_stale_snapshot_and_keeps_own_check(self):
        self.refresh()
        before = (self.data / 'uf.json').read_bytes()
        national_before = [(self.data / name).read_bytes() for name in ('history.json', 'status.json')]
        page = self.refresh(national=UnavailableNational(), uf=ExportSource(run=7), day=1)
        self.assertEqual(self.counts(page), RANKED)
        self.assertEqual((self.data / 'uf.json').read_bytes(), before)
        self.assertEqual([(self.data / name).read_bytes() for name in ('history.json', 'status.json')], national_before)
        self.assertEqual(page.text(id='uf-check'), '15/11/2026 às 09:00 (Brasília, UTC−03:00)')
        self.assertEqual(page.one(id='uf-retrieved')['attrs']['datetime'], '2026-11-14T05:56:04.896Z')
        self.assertIn('fbffe323c3485bed0024afe6133f450dc20f51ab8c7aba65a1079be6476e345c', page.text(id='uf-panel'))
        self.assertNotIn('5f88f93738b41b035a4bf58450292366afd2aa28b66019c8103e079c0aa6fb55', page.text(id='uf-panel'))
        self.assertEqual(page.text(id='vacant-count'), '87')
        self.assertEqual(page.one('aside')['text'].count('14/11/2026 às 09:00'), 1)

    def test_source_zeros_have_zero_bars_exact_table_and_alphabetical_ties(self):
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        def zero(root):
            for row in root.find(ns + 'sheetData')[1:]:
                row.find(ns + 'c[@r="G' + row.get('r') + '"]/' + ns + 'v').text = '0'
        evidence = deepcopy(ExportSource().evidence)
        evidence['snapshot']['qGrandTotalRow'][0]['qNum'] = 0
        page = self.refresh(uf=ExportSource(content=workbook_variant(zero), evidence=evidence))
        self.assertEqual(self.counts(page), [(uf, 0) for uf in (
            'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS',
            'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO')])
        tracks = page.matching('span', **{'class': 'uf-track'})
        self.assertEqual(len(tracks), 27)
        fills = [n for n in page.matching('span') if any(t in n['parents'] for t in tracks)]
        self.assertEqual([n['attrs']['style'] for n in fills], ['width: 0.000000%'] * 27)
        self.assertIn('Total: 0 PCFs ativos', page.text(id='uf-panel'))

    def test_invalid_coverage_unknown_and_suppressed_are_not_zero_and_retain_uf_dates(self):
        self.refresh()
        before = [(self.data / name).read_bytes() for name in ('uf.json', 'uf-status.json')]
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        for kind in ('missing', 'unknown', 'suppressed'):
            def invalid(root):
                if kind == 'missing':
                    sheet = root.find(ns + 'sheetData')
                    sheet.remove(list(sheet)[1])
                else:
                    ref, value = ('F2', 'XX') if kind == 'unknown' else ('G2', '*')
                    cell = root.find('.//' + ns + f'c[@r="{ref}"]')
                    cell.set('t', 'inlineStr')
                    cell[:] = []
                    ET.SubElement(ET.SubElement(cell, ns + 'is'), ns + 't').text = value
            with self.subTest(kind=kind):
                page = self.refresh(national=ControlledArchive(dict([monthly_resource('2026-10')])),
                                    uf=ExportSource(content=workbook_variant(invalid)), day=1)
                self.assertEqual(self.counts(page), RANKED)
                self.assertEqual([(self.data / name).read_bytes() for name in ('uf.json', 'uf-status.json')], before)
                self.assertEqual(page.text(id='uf-check'), '14/11/2026 às 09:00 (Brasília, UTC−03:00)')
                self.assertEqual(page.one('time', id='uf-reference')['attrs']['datetime'], '2026-09')
                self.assertEqual(page.text(id='vacant-count'), '87')
                self.assertEqual(page.one('time', datetime='2026-10')['text'], 'outubro de 2026')

    def test_new_latest_month_replaces_uf_view_without_adding_a_history(self):
        self.refresh()
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        def october(root):
            for row in root.find(ns + 'sheetData')[1:]:
                cell = row.find(ns + 'c[@r="B' + row.get('r') + '"]')
                cell.set('t', 'inlineStr')
                cell[:] = []
                ET.SubElement(ET.SubElement(cell, ns + 'is'), ns + 't').text = 'Out'
        evidence = deepcopy(ExportSource().evidence)
        evidence['snapshot']['latest'] = {'qText': 'Out 2026', 'qNum': 46296}
        evidence['available_periods'].append({'qText': 'Out 2026', 'qNum': 46296, 'qState': 'O'})
        evidence['snapshot']['availablePeriodCount'] += 1
        next(s for s in evidence['snapshot']['finalSelections'] if s['label'] == 'Mês/Ano')['selected'] = ['Out 2026']
        # A deliberately different national measure/reference must not supply UF values.
        page = self.refresh(national=ControlledArchive({SEPTEMBER_URL: national_counts('2026-09', 900, 295)}),
                            uf=ExportSource(content=workbook_variant(october), evidence=evidence), day=1)
        self.assertEqual(page.text(id='vacant-count'), '295')
        self.assertIn('900', page.text(id='current-values'))
        self.assertEqual(page.text(id='uf-reference'), 'outubro de 2026')
        self.assertNotIn('setembro de 2026', page.text(id='uf-panel'))
        self.assertEqual(self.counts(page), RANKED)
        self.assertEqual(len(page.matching('table', id='uf-values')), 1)
        self.assertFalse(page.matching('select'))
        self.assertFalse(page.matching('svg', id='uf-history'))

    def test_first_absence_in_either_direction_does_not_invent_values_checks_or_links(self):
        page = self.refresh(uf=UnavailableUF())
        self.assertIn('ausência não é zero', page.text('body'))
        self.assertFalse(page.matching(id='uf-bars'))
        self.assertFalse(page.matching('a', href='data/uf.json'))
        self.assertFalse(page.matching('a', href='data/uf-status.json'))
        self.assertFalse((self.site / 'data/uf.json').exists())
        self.assertEqual(page.text(id='vacant-count'), '87')
        self.data, self.site = self.root / 'only-uf-data', self.root / 'only-uf-site'
        page = self.refresh(national=UnavailableNational())
        self.assertEqual(self.counts(page), RANKED)
        self.assertIn('Verificação nacional indisponível', page.text('body'))
        self.assertFalse(page.matching(id='vacant-count'))
        self.assertFalse(page.matching('a', href='data/history.json'))
        self.assertFalse(page.matching('a', href='data/status.json'))
        self.assertFalse((self.site / 'data/status.json').exists())


if __name__ == '__main__':
    unittest.main()
