"""Prospective UF retention through the complete public refresh/build seam.

Modified periods/counts below are COUNTERFACTUAL, not official observations.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from perito_dashboard import refresh_and_build
from tests.sources import ControlledArchive, UnavailableUF
from tests.test_uf import ExportSource, NOW, UnavailableNational, workbook_variant

ROOT = Path(__file__).resolve().parents[1]
UF_FILES = ('uf.json', 'uf-status.json', 'uf-history.json')


def counterfactual(month='2026-09', ac_first=1):
    """Independently edit external workbook/receipts; never production helpers."""
    from xml.etree import ElementTree as ET
    ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    year, number = map(int, month.split('-'))
    label = ('Jan Fev Mar Abr Mai Jun Jul Ago Set Out Nov Dez'.split()[number - 1])
    def edit(root):
        for row in root.findall(ns + 'sheetData/' + ns + 'row')[1:]:
            cells = row.findall(ns + 'c')
            for cell, value in ((cells[0], str(year)), (cells[1], label)):
                cell.clear()
                cell.set('r', ('A' if cell is cells[0] else 'B') + row.get('r'))
                cell.set('t', 'inlineStr')
                ET.SubElement(ET.SubElement(cell, ns + 'is'), ns + 't').text = value
        root.find('.//' + ns + 'c[@r="G2"]/' + ns + 'v').text = str(ac_first)
    content = workbook_variant(edit)
    evidence = ExportSource().evidence
    serial = (datetime(year, number, 1) - datetime(1899, 12, 30)).days
    def replace(value):
        if isinstance(value, dict):
            return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        if value == 'Set 2026':
            return label + ' ' + str(year)
        if type(value) is int and value == 46266:
            return serial
        return value
    evidence = replace(evidence)
    evidence['snapshot']['qGrandTotalRow'][0]['qNum'] = 1107 + ac_first
    return ExportSource(content=content, evidence=evidence)


class UFHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.site = self.root / 'data', self.root / 'site'

    def refresh(self, uf=None, national=None, day=1):
        return refresh_and_build(self.data, self.site,
            source=national if national is not None else ControlledArchive(),
            uf_source=uf if uf is not None else ExportSource(),
            clock=lambda: NOW + timedelta(days=day))

    def saved(self, name='uf-history.json'):
        self.assertEqual((self.data / name).read_bytes(), (self.site / 'data' / name).read_bytes())
        return json.loads((self.data / name).read_text())

    def output_state(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mode)
                for p in self.root.rglob('*') if p.is_file()}

    def genuine_legacy(self):
        self.data.mkdir()
        for name in ('uf.json', 'uf-status.json'):
            shutil.copy2(ROOT / 'data' / name, self.data / name)
        return json.loads((self.data / 'uf.json').read_text())['current']

    def test_genuine_accepted_current_migrates_without_rewriting_original_evidence(self):
        original = self.genuine_legacy()
        before = (self.data / 'uf.json').read_bytes()
        self.refresh()
        archive = self.saved()
        self.assertEqual(archive['schema_version'], 1)
        self.assertEqual(archive['observations'], [original])
        self.assertEqual(archive['coverage'], {'available_months': ['2026-09'],
            'start': '2026-09', 'end': '2026-09', 'missing_months': []})
        self.assertEqual(archive['corrections'], [])
        self.assertEqual(archive['legacy_corrections'], [])
        self.assertEqual(original['total'], 1108)
        self.assertEqual(original['counts_by_uf']['DF'], 324)
        self.assertEqual((self.data / 'uf.json').read_bytes(), before)
        raw = (self.data / 'uf-history.json').read_bytes()
        self.refresh(uf=ExportSource(run=7), day=2)
        self.assertEqual((self.data / 'uf-history.json').read_bytes(), raw)

    def test_full_correction_transitions_then_rollover_and_year_gaps(self):
        self.refresh()
        first = self.saved()['observations'][0]
        self.refresh(uf=counterfactual(ac_first=0), day=2)
        archive = self.saved()
        second = archive['observations'][0]
        self.assertEqual(second['total'], 1107)
        self.assertEqual(second['counts_by_uf']['AC'], 8)
        self.assertEqual(archive['corrections'], [{'superseded': first, 'replacement': second,
            'corrected_at': '2026-11-16T12:00:00Z'}])
        self.refresh(uf=counterfactual(ac_first=2), day=3)
        third = self.saved()['observations'][0]
        self.assertEqual(third['total'], 1109)
        self.assertEqual(third['counts_by_uf']['AC'], 10)
        self.assertEqual(self.saved()['corrections'][1], {'superseded': second, 'replacement': third,
            'corrected_at': '2026-11-17T12:00:00Z'})
        audit = self.saved()['corrections']
        self.refresh(uf=counterfactual('2027-01'), day=100)
        archive = self.saved()
        self.assertEqual(archive['observations'][0], third)
        self.assertEqual(archive['observations'][1]['reference_month'], '2027-01')
        self.assertEqual(archive['coverage'], {'available_months': ['2026-09', '2027-01'],
            'start': '2026-09', 'end': '2027-01', 'missing_months': ['2026-10', '2026-11', '2026-12']})
        self.assertEqual(archive['corrections'], audit)
        self.assertEqual(self.saved('uf.json')['current'], archive['observations'][-1])
        self.assertEqual(self.saved('uf.json')['corrections'], [])
        before = (self.data / 'uf-history.json').read_bytes()
        result = self.refresh(uf=counterfactual('2027-01'), day=101)
        self.assertEqual(result['uf'], 'unchanged')
        self.assertEqual((self.data / 'uf-history.json').read_bytes(), before)

    def test_migration_keeps_actual_B_and_legacy_A_without_inventing_A_to_B(self):
        self.refresh()
        first = self.saved()['observations'][0]
        self.refresh(uf=counterfactual(ac_first=0), day=2)
        second = self.saved('uf.json')['current']
        legacy = self.saved('uf.json')['corrections']
        (self.data / 'uf-history.json').unlink()  # simulate the real UFv1 format
        self.refresh(uf=counterfactual(ac_first=2), day=3)
        archive = self.saved()
        third = archive['observations'][0]
        self.assertEqual(archive['legacy_corrections'], legacy)
        self.assertEqual(legacy, [{'superseded': first, 'corrected_at': '2026-11-16T12:00:00Z'}])
        self.assertEqual(archive['corrections'], [{'superseded': second, 'replacement': third,
            'corrected_at': '2026-11-17T12:00:00Z'}])
        self.assertEqual(third['total'], 1109)

    def test_migration_stages_actual_B_before_new_month_C_and_retains_legacy_A(self):
        self.refresh()
        self.refresh(uf=counterfactual(ac_first=0), day=2)
        B = self.saved('uf.json')['current']
        legacy = self.saved('uf.json')['corrections']
        (self.data / 'uf-history.json').unlink()
        self.refresh(uf=counterfactual('2026-10'), day=3)
        archive = self.saved()
        self.assertEqual(archive['observations'][0], B)
        self.assertEqual([r['reference_month'] for r in archive['observations']], ['2026-09', '2026-10'])
        self.assertEqual([r['total'] for r in archive['observations']], [1107, 1108])
        self.assertEqual(archive['legacy_corrections'], legacy)
        self.assertEqual(archive['corrections'], [])  # rollover is not a correction
        raw = (self.data / 'uf-history.json').read_bytes()
        self.refresh(uf=counterfactual('2026-10'), day=4)
        self.assertEqual((self.data / 'uf-history.json').read_bytes(), raw)

    def test_whole_UF_zero_is_retained_but_invalid_population_geography_and_values_are_not(self):
        from xml.etree import ElementTree as ET
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        self.refresh()
        def zero_AC(root):
            for row in root.findall(ns + 'sheetData/' + ns + 'row')[1:]:
                cells = row.findall(ns + 'c')
                if cells[5].get('t') == 's' and cells[5].find(ns + 'v').text == '11':
                    cells[6].find(ns + 'v').text = '0'
        # AC is shared-string index 11 in the authentic source document.
        zero = ExportSource(content=workbook_variant(zero_AC))
        zero.evidence['snapshot']['qGrandTotalRow'][0]['qNum'] = 1099
        self.assertEqual(self.refresh(uf=zero, day=2)['uf'], 'updated')
        row = self.saved()['observations'][0]
        self.assertEqual(row['counts_by_uf']['AC'], 0)
        self.assertEqual(row['counts_by_uf']['DF'], 324)
        self.assertEqual(row['total'], 1099)
        self.assertEqual(len(row['counts_by_uf']), 27)
        def text(cell, value):
            address = cell.get('r')
            cell.clear()
            cell.set('r', address)
            cell.set('t', 'inlineStr')
            ET.SubElement(ET.SubElement(cell, ns + 'is'), ns + 't').text = value
        for address, value in [('C2', 'Inativo'), ('D2', 'Outro cargo'), ('E2', 'OUTRO'),
                               ('F2', 'ZZ'), ('G2', '***'), ('G2', '-1')]:
            with self.subTest(address=address, value=value):
                source = ExportSource(content=workbook_variant(
                    lambda root: text(root.find('.//' + ns + 'c[@r="' + address + '"]'), value)))
                before = self.output_state()
                self.assertEqual(self.refresh(uf=source, day=3)['uf'], 'failed')
                after = self.output_state()
                for path, state in before.items():
                    if Path(path).name in UF_FILES:
                        self.assertEqual(after[path], state)

    def test_corrupt_saved_archive_rejected_globally_before_either_source(self):
        self.refresh()
        self.refresh(uf=counterfactual(ac_first=0), day=2)
        self.refresh(uf=counterfactual(ac_first=2), day=3)
        original = self.saved()
        class Untouched:
            def archive_index(self):
                raise AssertionError('national source called before validation')
            def latest_export(self):
                raise AssertionError('UF source called before validation')
        def bad_row(a):
            a['observations'][0]['total'] = 0
        def bad_provenance(a):
            a['corrections'][0]['replacement']['source']['sha256'] = 'bad'
        mutations = [bad_row, bad_provenance,
            lambda a: a['observations'][0]['geography'].update(officially_verified=True),
            lambda a: a.update(schema_version=True),
            lambda a: a.update(observations=[]),
            lambda a: a['observations'].append(deepcopy(a['observations'][0])),
            lambda a: a['coverage'].update(missing_months=['2026-10']),
            lambda a: a['corrections'][0].update(corrected_at='2026-11-13T00:00:00Z'),
            lambda a: a['corrections'][0].update(corrected_at='2027-01-01T00:00:00Z'),
            lambda a: a['corrections'][0].pop('replacement'),
            lambda a: a['corrections'][0].update(extra='untrusted'),
            lambda a: a['corrections'].reverse(),
            lambda a: a['corrections'].pop(),
            lambda a: a.update(corrections=[]),
            lambda a: a.update(legacy_corrections=[{'superseded': a['observations'][0],
                'corrected_at': 'broken'}]),
            lambda a: a.update(legacy_corrections='not a list')]
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                broken = deepcopy(original)
                mutation(broken)
                (self.data / 'uf-history.json').write_text(json.dumps(broken))
                before = self.output_state()
                with self.assertRaises(ValueError):
                    self.refresh(uf=Untouched(), national=Untouched(), day=4)
                self.assertEqual(self.output_state(), before)
        (self.data / 'uf-history.json').write_text(json.dumps(original))

    def test_feed_failure_preserves_uf_bytes_modes_and_archive_absence_or_presence(self):
        from tests.sources import monthly_resource
        self.genuine_legacy()
        for with_archive in (False, True):
            if with_archive:
                self.refresh(day=5)
            for name in UF_FILES:
                if (self.data / name).exists():
                    (self.data / name).chmod(0o640)
                if (self.site / 'data' / name).exists():
                    (self.site / 'data' / name).chmod(0o600)
            before = self.output_state()
            result = self.refresh(uf=UnavailableUF(), day=6 if with_archive else 4,
                national=ControlledArchive(dict([monthly_resource('2026-10')])))
            self.assertEqual(result['uf'], 'failed')
            self.assertEqual(result['publication'], 'partial')
            after = self.output_state()
            for path, state in before.items():
                if Path(path).name in UF_FILES:
                    self.assertEqual(after[path], state)
            self.assertEqual((self.data / 'uf-history.json').exists(), with_archive)
            self.assertEqual(self.saved('history.json')['observations'][-1]['reference_month'], '2026-10')

    def test_regressed_latest_cannot_change_archive_or_uf_check(self):
        self.refresh(uf=counterfactual('2027-01'), day=100)
        before = self.output_state()
        result = self.refresh(day=101)
        self.assertEqual(result['uf'], 'failed')
        after = self.output_state()
        for path, state in before.items():
            if Path(path).name in UF_FILES:
                self.assertEqual(after[path], state)

    def test_each_month_correction_audits_survive_later_months_and_old_source_attempts(self):
        self.refresh()
        september_A = self.saved()['observations'][0]
        self.refresh(uf=counterfactual(ac_first=0), day=2)
        september_B = self.saved()['observations'][0]
        self.refresh(uf=counterfactual('2026-10'), day=3)
        october_C = self.saved()['observations'][1]
        self.refresh(uf=counterfactual('2026-10', ac_first=2), day=4)
        archive = self.saved()
        october_D = archive['observations'][1]
        self.assertEqual([r['reference_month'] for r in archive['observations']], ['2026-09', '2026-10'])
        self.assertEqual([r['total'] for r in archive['observations']], [1107, 1109])
        self.assertEqual(archive['corrections'], [
            {'superseded': september_A, 'replacement': september_B, 'corrected_at': '2026-11-16T12:00:00Z'},
            {'superseded': october_C, 'replacement': october_D, 'corrected_at': '2026-11-18T12:00:00Z'}])
        raw = (self.data / 'uf-history.json').read_bytes()
        self.refresh(uf=counterfactual('2026-10', ac_first=2), day=5)
        self.assertEqual((self.data / 'uf-history.json').read_bytes(), raw)
        self.refresh(uf=counterfactual(ac_first=2), day=6)
        self.assertEqual((self.data / 'uf-history.json').read_bytes(), raw)
        self.assertEqual(self.saved('uf.json')['current'], october_D)
        self.assertEqual(self.saved('uf.json')['corrections'],
            [{'superseded': october_C, 'corrected_at': '2026-11-18T12:00:00Z'}])

    def test_timeout_during_migration_never_materializes_bootstrap(self):
        self.genuine_legacy()
        original = {n: (self.data / n).read_bytes() for n in ('uf.json', 'uf-status.json')}
        class TimeoutExport:
            def latest_export(self):
                raise TimeoutError('controlled timeout')
        result = self.refresh(uf=TimeoutExport())
        self.assertEqual(result['publication'], 'partial')
        self.assertFalse((self.data / 'uf-history.json').exists())
        self.assertFalse((self.site / 'data/uf-history.json').exists())
        self.assertEqual({n: (self.data / n).read_bytes() for n in original}, original)

    def test_archive_link_single_point_and_gaps_are_honest_and_subpath_relative(self):
        from tests.test_dashboard import Page
        self.refresh()
        page = Page((self.site / 'index.html').read_text())
        self.assertTrue(page.matching('a', href='data/uf-history.json'))
        self.assertIn('Uma única observação não permite inferir tendência', page.text(id='uf-coverage'))
        self.assertIn('setembro de 2026', page.text(id='uf-coverage'))
        self.assertNotIn('Somente o retrato mais recente aceito, sem série histórica UF.', page.text(id='uf-panel'))
        self.refresh(uf=counterfactual('2027-01'), day=100)
        page = Page((self.site / 'index.html').read_text())
        self.assertIn('outubro de 2026, novembro de 2026, dezembro de 2026', page.text(id='uf-coverage'))
        self.assertIn('não são zeros', page.text(id='uf-coverage'))
        self.assertEqual(page.one(id='uf-reference')['attrs']['datetime'], '2027-01')
        self.assertEqual(len(page.matching('ol', id='uf-bars')), 1)
        self.assertEqual(len(page.matching('table', id='uf-values')), 1)
        self.assertFalse(page.matching('svg', id='uf-history'))
        for anchor in page.matching('a'):
            href = anchor['attrs'].get('href', '')
            if 'uf-history.json' in href:
                self.assertEqual(href, 'data/uf-history.json')
        self.saved()

    def test_real_shared_filesystem_failure_and_stale_clock_preserve_every_byte_and_mode(self):
        self.refresh()
        before = self.output_state()
        with self.assertRaisesRegex(ValueError, 'Stale refresh'):
            self.refresh(day=0)
        self.assertEqual(self.output_state(), before)
        self.root.chmod(0o500)
        try:
            with self.assertRaises(PermissionError):
                self.refresh(uf=counterfactual(ac_first=0), day=2)
        finally:
            self.root.chmod(0o700)
        self.assertEqual(self.output_state(), before)

    def test_overlapping_public_writers_refuse_second_without_altering_outputs(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        self.refresh()
        entered, release = Event(), Event()
        class WaitingExport(ExportSource):
            def latest_export(self):
                entered.set()
                if not release.wait(10):
                    raise TimeoutError('controlled wait expired')
                return super().latest_export()
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.refresh, WaitingExport(), day=2)
            try:
                self.assertTrue(entered.wait(5))
                before = self.output_state()
                with self.assertRaisesRegex(ValueError, 'Concurrent refresh'):
                    self.refresh(day=3)
                self.assertEqual(self.output_state(), before)
            finally:
                release.set()
            self.assertEqual(first.result()['publication'], 'complete')

    def test_mode_only_stale_external_write_is_detected_before_promotion(self):
        self.refresh()
        before = self.output_state()
        class EditingExport(ExportSource):
            def latest_export(inner):
                (self.data / 'uf-history.json').chmod(0o600)
                return super().latest_export()
        with self.assertRaisesRegex(ValueError, 'Stale refresh'):
            self.refresh(uf=EditingExport(), day=2)
        (self.data / 'uf-history.json').chmod(before['data/uf-history.json'][1] & 0o777)
        self.assertEqual(self.output_state(), before)

    def test_current_C_only_bootstrap_does_not_reconstruct_lost_B_or_audit_A(self):
        self.refresh()
        self.refresh(uf=counterfactual(ac_first=0), day=2)
        self.refresh(uf=counterfactual('2026-10'), day=3)
        current = self.saved('uf.json')['current']
        (self.data / 'uf-history.json').unlink()
        self.refresh(uf=counterfactual('2026-10'), day=4)
        archive = self.saved()
        self.assertEqual(archive['observations'], [current])
        self.assertEqual(archive['legacy_corrections'], [])
        self.assertEqual(archive['corrections'], [])
        self.assertEqual(archive['coverage'], {'available_months': ['2026-10'],
            'start': '2026-10', 'end': '2026-10', 'missing_months': []})

    def test_first_absence_and_legacy_crossmonth_are_not_normalized(self):
        self.refresh(uf=UnavailableUF())
        self.assertFalse((self.data / 'uf-history.json').exists())
        self.assertFalse((self.site / 'data/uf-history.json').exists())
        self.refresh(day=2)
        september = self.saved('uf.json')['current']
        self.refresh(uf=counterfactual('2026-10'), day=3)
        (self.data / 'uf-history.json').unlink()
        current = self.saved('uf.json')
        current['corrections'] = [{'superseded': september, 'corrected_at': '2026-11-17T12:00:00Z'}]
        (self.data / 'uf.json').write_text(json.dumps(current))
        before = self.output_state()
        with self.assertRaises(ValueError):
            self.refresh(day=4)
        self.assertEqual(self.output_state(), before)

    def test_healthy_uf_can_advance_while_national_fails(self):
        self.refresh()
        before = {n: (self.data / n).read_bytes() for n in ('history.json', 'status.json')}
        result = self.refresh(uf=counterfactual('2026-10'), national=UnavailableNational(), day=2)
        self.assertEqual(result, {'national': 'failed', 'uf': 'updated', 'publication': 'partial'})
        self.assertEqual(self.saved()['coverage']['available_months'], ['2026-09', '2026-10'])
        self.assertEqual({n: (self.data / n).read_bytes() for n in before}, before)
