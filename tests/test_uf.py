"""Complete refresh/build acceptance using genuine public aggregate documents."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import tarfile
from unittest.mock import patch
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from perito_dashboard import refresh_and_build
from tests.sources import ControlledArchive, UnavailableUF
from tests.uf_runtime import install_offline_runtime

FIXTURES = Path(__file__).parent / 'fixtures/uf'
NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


class ExportSource:
    def __init__(self, run=6, content=None, evidence=None):
        self.content = content if content is not None else (FIXTURES / f'run-{run}.xlsx').read_bytes()
        self.evidence = deepcopy(evidence) if evidence is not None else json.loads((FIXTURES / f'run-{run}.json').read_text())
        if content is not None:
            # A controlled modified export also has its own transport receipt.
            # Source row counts/population/total claims are NOT auto-adjusted.
            for event in self.evidence['trace']:
                if event['kind'] == 'Browser.downloadProgress' and event['state'] == 'completed':
                    event['receivedBytes'] = event['totalBytes'] = len(content)

    def latest_export(self):
        from perito_dashboard import UFExport
        return UFExport(self.content, deepcopy(self.evidence))


class UnavailableNational:
    def archive_index(self):
        raise ValueError('controlled national source unavailable')


def workbook_variant(edit):
    """Controlled OOXML mutation of the genuine document, not production helpers."""
    content = (FIXTURES / 'run-6.xlsx').read_bytes()
    output = BytesIO()
    with ZipFile(BytesIO(content)) as source, ZipFile(output, 'w') as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                root = ET.fromstring(data)
                edit(root)
                data = ET.tostring(root, encoding='utf-8')
            target.writestr(item, data)
    return output.getvalue()


class UFAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data, self.site = self.root / 'data', self.root / 'site'

    def refresh(self, national=None, uf=None, day=0):
        return refresh_and_build(self.data, self.site,
                                 source=national if national is not None else ControlledArchive(),
                                 uf_source=uf if uf is not None else ExportSource(),
                                 clock=lambda: NOW + timedelta(days=day))

    def saved(self, name):
        path = self.data / name
        self.assertEqual(path.read_bytes(), (self.site / 'data' / name).read_bytes())
        return json.loads(path.read_text())

    def bytes(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_malformed_compression_and_unknown_encoding_are_isolated_uf_failures(self):
        from tests.sources import monthly_resource
        original = ExportSource().content
        broken_deflate = bytearray(original)
        with ZipFile(BytesIO(original)) as archive:
            item = archive.getinfo('xl/worksheets/sheet1.xml')
            offset = item.header_offset
            name_size, extra_size = struct.unpack_from('<HH', original, offset + 26)
            # BFINAL=1, BTYPE=3 is an invalid DEFLATE block, not just a CRC error.
            broken_deflate[offset + 30 + name_size + extra_size] = 7
        output = BytesIO()
        with ZipFile(BytesIO(original)) as source, ZipFile(output, 'w') as target:
            for item in source.infolist():
                content = source.read(item.filename)
                if item.filename == 'xl/worksheets/sheet1.xml':
                    content = content.replace(b'encoding="UTF-8"', b'encoding="BOGUS"')
                    self.assertIn(b'encoding="BOGUS"', content)
                target.writestr(item, content)
        for case, content in [('deflate', bytes(broken_deflate)), ('encoding', output.getvalue())]:
            for last_good in (False, True):
                with self.subTest(case=case, last_good=last_good):
                    root = self.root / (case + str(last_good))
                    root.mkdir()
                    data, site = root / 'data', root / 'site'
                    if last_good:
                        refresh_and_build(data, site, source=ControlledArchive(),
                                          uf_source=ExportSource(), clock=lambda: NOW)
                    before = {name: (data / name).read_bytes() for name in ('uf.json', 'uf-status.json')
                              if (data / name).exists()}
                    malformed = ExportSource(content=content)
                    (root / 'malformed.xlsx').write_bytes(content)
                    (root / 'malformed.json').write_text(json.dumps(malformed.evidence))
                    env = install_offline_runtime(root, [{'workbook': str(root / 'malformed.xlsx'),
                                                         'evidence': str(root / 'malformed.json')}])
                    with patch.dict(os.environ, env):
                        result = refresh_and_build(data, site,
                            source=ControlledArchive(dict([monthly_resource('2026-10')])),
                            clock=lambda: NOW + timedelta(days=1))
                    self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
                    self.assertEqual(json.loads((data / 'history.json').read_text())['observations'][-1]['reference_month'], '2026-10')
                    for name in ('uf.json', 'uf-status.json'):
                        if last_good:
                            self.assertEqual((data / name).read_bytes(), before[name])
                            self.assertEqual((site / 'data' / name).read_bytes(), before[name])
                        else:
                            self.assertFalse((data / name).exists())
                            self.assertFalse((site / 'data' / name).exists())
                    self.assertIn('Cargos vagos', (site / 'index.html').read_text())

    def test_utf16_entity_workbooks_cannot_enter_complete_publication(self):
        from tests.sources import monthly_resource
        for encoding in ('utf-16', 'utf-16-be', 'utf-16-le'):
            with self.subTest(encoding=encoding):
                root = self.root / encoding
                root.mkdir()
                data, site = root / 'data', root / 'site'
                refresh_and_build(data, site, source=ControlledArchive(),
                                  uf_source=ExportSource(), clock=lambda: NOW)
                before = {name: (data / name).read_bytes() for name in ('uf.json', 'uf-status.json')}
                output = BytesIO()
                with ZipFile(BytesIO(ExportSource().content)) as source, ZipFile(output, 'w') as target:
                    for item in source.infolist():
                        content = source.read(item.filename)
                        if item.filename == 'xl/worksheets/sheet1.xml':
                            text = content.decode('utf-8').replace('encoding="UTF-8"', 'encoding="UTF-16"')
                            text = text.replace('<worksheet ', '<!DOCTYPE worksheet [<!ENTITY count "1">]>\n<worksheet ', 1)
                            text = text.replace('<v>1</v>', '<v>&count;</v>', 1)
                            content = text.encode(encoding)
                        target.writestr(item, content)
                content = output.getvalue()
                malformed = ExportSource(content=content)
                (root / 'malformed.xlsx').write_bytes(content)
                (root / 'malformed.json').write_text(json.dumps(malformed.evidence))
                env = install_offline_runtime(root, [
                    {'workbook': str(root / 'malformed.xlsx'), 'evidence': str(root / 'malformed.json')},
                    {'workbook': str(FIXTURES.resolve() / 'run-7.xlsx'),
                     'evidence': str(FIXTURES.resolve() / 'run-7.json')}])
                with patch.dict(os.environ, env):
                    result = refresh_and_build(data, site,
                        source=ControlledArchive(dict([monthly_resource('2026-10')])),
                        clock=lambda: NOW + timedelta(days=1))
                self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
                for name, raw in before.items():
                    self.assertEqual((data / name).read_bytes(), raw)
                    self.assertEqual((site / 'data' / name).read_bytes(), raw)
                self.assertEqual(json.loads((data / 'history.json').read_text())['observations'][-1]['reference_month'], '2026-10')
                self.assertIn('1.108 PCFs ativos', (site / 'index.html').read_text())

    def test_partial_refresh_emits_actionable_sanitized_per_feed_diagnostics(self):
        for case, code in [('invalid', 'invalid_export'), ('denial', 'source_denied'),
                           ('runtime', 'runtime_unavailable'), ('transport', 'collection_failed')]:
            with self.subTest(case=case):
                root = self.root / case
                root.mkdir()
                malformed = ExportSource(content=b'not an XLSX') if case == 'invalid' else ExportSource()
                if case == 'denial':
                    next(e for e in malformed.evidence['trace'] if e['kind'] == 'ws_handshake')['status'] = 403
                (root / 'candidate.xlsx').write_bytes(malformed.content)
                (root / 'candidate.json').write_text(json.dumps(malformed.evidence))
                env = install_offline_runtime(root, [{'workbook': str(root / 'candidate.xlsx'),
                                                     'evidence': str(root / 'candidate.json')}])
                if case == 'runtime':
                    env['PERITO_NODE'] = '/nonexistent/private-token-node'
                class SensitiveOutage:
                    def latest_export(self):
                        raise ValueError('cookie=SECRET csrf=SECRET DevTools profile /tempcontent/SECRET ' * 500)
                with patch.dict(os.environ, env), self.assertLogs('perito_dashboard', level='WARNING') as messages:
                    kwargs = {'uf_source': SensitiveOutage()} if case == 'transport' else {}
                    result = refresh_and_build(root / 'data', root / 'site', source=ControlledArchive(),
                                               clock=lambda: NOW, **kwargs)
                self.assertEqual(result['publication'], 'partial')
                text = '\n'.join(messages.output)
                self.assertIn('uf: ' + code, text)
                self.assertIn('check ', text)
                self.assertLess(len(text), 500)
                for forbidden in ('SECRET', 'cookie', 'csrf', 'DevTools', 'profile', 'tempcontent', 'private-token'):
                    self.assertNotIn(forbidden, text)
                self.assertTrue((root / 'site/data/history.json').exists())
                self.assertFalse((root / 'data/uf-status.json').exists())
        # Opposite direction also exposes a safe reason while accepting UF.
        with self.assertLogs('perito_dashboard', level='WARNING') as messages:
            result = self.refresh(national=UnavailableNational())
        self.assertEqual(result['publication'], 'partial')
        self.assertIn('national: source_unavailable_or_invalid', '\n'.join(messages.output))

    def test_changed_actual_runtime_receipt_rejects_only_uf_after_two_exports(self):
        from tests.sources import monthly_resource
        self.refresh()
        before = {name: (self.data / name).read_bytes() for name in ('uf.json', 'uf-status.json')}
        env = install_offline_runtime(self.root, [
            {'workbook': str(FIXTURES.resolve() / f'run-{run}.xlsx'),
             'evidence': str(FIXTURES.resolve() / f'run-{run}.json')} for run in (6, 7)])
        # External executable boundary: it changes its own bytes on acquisition,
        # not on --version. No production runtime/collector method is patched.
        runtime = Path(env['PERITO_NODE'])
        runtime.write_text(runtime.read_text().replace('import runpy\n',
            "import runpy, sys\nif sys.argv[1:] != ['--version']:\n"
            "    with open(__file__, 'a') as executable: executable.write('# changed\\n')\n"))
        with patch.dict(os.environ, env), self.assertLogs('perito_dashboard', level='WARNING') as messages:
            result = refresh_and_build(self.data, self.site,
                                       source=ControlledArchive(dict([monthly_resource('2026-10')])),
                                       clock=lambda: NOW + timedelta(days=1))
        self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
        self.assertIn('uf: runtime_integrity; check ', '\n'.join(messages.output))
        self.assertEqual(Path(env['PERITO_TEST_EXPORT_SEQUENCE']).with_suffix('.count').read_text(), '2')
        for name, raw in before.items():
            self.assertEqual((self.data / name).read_bytes(), raw)
            self.assertEqual((self.site / 'data' / name).read_bytes(), raw)
        self.assertEqual(self.saved('history.json')['observations'][-1]['reference_month'], '2026-10')

    def test_download_receipt_binds_well_formed_guid_and_actual_document_size(self):
        for field in ('guid', 'size'):
            evidence = deepcopy(ExportSource().evidence)
            for event in evidence['trace']:
                if event['kind'].startswith('Browser.download'):
                    if field == 'guid':
                        event['guid'] = 'not-a-browser-guid'
                    elif event.get('state') == 'completed':
                        event['receivedBytes'] = event['totalBytes'] = 7916
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'download'):
                self.refresh(national=UnavailableNational(), uf=ExportSource(evidence=evidence))
            self.assertEqual(self.bytes(), {})

    def test_numeric_latest_period_must_correspond_to_returned_calendar_month(self):
        evidence = deepcopy(ExportSource().evidence)
        # All source claims consistently use an October serial but September label.
        evidence['snapshot']['latest']['qNum'] = 46296
        for period in evidence['available_periods']:
            if period['qText'] == 'Set 2026':
                period['qNum'] = 46296
        with self.assertRaisesRegex(ValueError, 'selected period'):
            self.refresh(national=UnavailableNational(), uf=ExportSource(evidence=evidence))
        self.assertEqual(self.bytes(), {})

    def test_external_workbook_relationship_is_rejected_without_publishing(self):
        output = BytesIO()
        with ZipFile(BytesIO(ExportSource().content)) as source, ZipFile(output, 'w') as target:
            for item in source.infolist():
                content = source.read(item.filename)
                if item.filename == 'xl/_rels/workbook.xml.rels':
                    content = content.replace(b'Target="worksheets/sheet1.xml"',
                                              b'Target="https://example.org/sheet.xml" TargetMode="External"')
                target.writestr(item, content)
        with self.assertRaisesRegex(ValueError, 'relationship|package'):
            self.refresh(national=UnavailableNational(), uf=ExportSource(content=output.getvalue()))
        self.assertEqual(self.bytes(), {})

    def test_default_production_adapter_uses_configured_owned_runtime_and_composes_uf(self):
        root = self.root / 'runtime with spaces'
        root.mkdir()
        env = install_offline_runtime(root, [
            {'workbook': str(FIXTURES.resolve() / f'run-{run}.xlsx'),
             'evidence': str(FIXTURES.resolve() / f'run-{run}.json')} for run in (6, 7)])
        with patch.dict(os.environ, env):
            result = refresh_and_build(self.data, self.site, source=UnavailableNational(), clock=lambda: NOW)
        self.assertEqual(result, {'national': 'failed', 'uf': 'updated', 'publication': 'partial'})
        self.assertEqual(self.saved('uf.json')['current']['counts_by_uf']['DF'], 324)
        self.assertIn('premissa do projeto', (self.site / 'index.html').read_text())

    def test_managed_runtime_setup_failure_is_inside_uf_candidate_not_global(self):
        # A file cannot be a runtime directory, on any host; never reaches network.
        blocked = self.root / 'not-a-runtime-directory'
        blocked.write_text('blocked')
        env = install_offline_runtime(self.root, [
            {'workbook': str(FIXTURES.resolve() / f'run-{run}.xlsx'),
             'evidence': str(FIXTURES.resolve() / f'run-{run}.json')} for run in (6, 7)])
        env['PERITO_RUNTIME_ROOT'] = str(blocked)
        with patch.dict(os.environ, env):
            result = refresh_and_build(self.data, self.site, source=ControlledArchive(), clock=lambda: NOW)
        self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
        self.assertEqual(self.saved('history.json')['observations'][-1]['reference_month'], '2026-09')
        self.assertFalse((self.data / 'uf.json').exists())

    def test_unsupported_managed_runtime_zip_preserves_uf_and_advances_national(self):
        from tests.sources import monthly_resource
        # Synthetic transport documents only: no publisher archive, real runtime
        # install, executable launch or network access. Exercise actual hash/size
        # verification and ZIP extraction, not a mocked installer/parser failure.
        node = BytesIO()
        with tarfile.open(fileobj=node, mode='w:xz') as archive:
            directory = tarfile.TarInfo('node-v0.0.0-linux-x64')
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
        chrome = BytesIO()
        with ZipFile(chrome, 'w') as archive:
            archive.writestr('chrome-linux64/chrome', b'OFFLINE synthetic non-executable')
        unsupported = bytearray(chrome.getvalue())
        struct.pack_into('<H', unsupported, 8, 99)  # Local compression method.
        struct.pack_into('<H', unsupported, unsupported.index(b'PK\x01\x02') + 10, 99)
        documents = {'https://offline.invalid/node.tar.xz': node.getvalue(),
                     'https://offline.invalid/chrome.zip': bytes(unsupported)}
        pins = {'python': {'version': platform.python_version()}}
        for name, url in zip(('node', 'chrome'), documents):
            pins[name] = {'version': 'v0.0.0', 'url': url, 'size': len(documents[url]),
                          'sha256': hashlib.sha256(documents[url]).hexdigest()}
        manifest = self.root / 'synthetic-runtime.json'
        manifest.write_text(json.dumps(pins))
        for last_good in (False, True):
            with self.subTest(last_good=last_good):
                root = self.root / str(last_good)
                data, site, runtime = root / 'data', root / 'site', root / 'runtime'
                if last_good:
                    refresh_and_build(data, site, source=ControlledArchive(), uf_source=ExportSource(),
                                      clock=lambda: NOW)
                before = {name: (data / name).read_bytes() for name in ('uf.json', 'uf-status.json')} if last_good else {}
                requested = []
                def response(url, **kwargs):
                    requested.append(url)
                    return BytesIO(documents[url])
                with patch.dict(os.environ, {'PERITO_RUNTIME_ROOT': str(runtime)}), \
                        patch('perito_dashboard.runtime.MANIFEST', manifest), \
                        patch('perito_dashboard.runtime.platform.system', return_value='Linux'), \
                        patch('perito_dashboard.runtime.platform.machine', return_value='x86_64'), \
                        patch('perito_dashboard.runtime.urlopen', side_effect=response), \
                        self.assertLogs('perito_dashboard', level='WARNING') as messages:
                    result = refresh_and_build(data, site,
                        source=ControlledArchive(dict([monthly_resource('2026-10')])),
                        clock=lambda: NOW + timedelta(days=1))
                self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
                self.assertEqual(requested, list(documents))
                self.assertIn('uf: runtime_setup; check ', '\n'.join(messages.output))
                self.assertEqual(json.loads((data / 'history.json').read_text())['observations'][-1]['reference_month'],
                                 '2026-10')
                self.assertEqual((data / 'history.json').read_bytes(), (site / 'data/history.json').read_bytes())
                self.assertIn('Cargos vagos', (site / 'index.html').read_text())
                for name in ('uf.json', 'uf-status.json'):
                    for path in (data / name, site / 'data' / name):
                        if last_good:
                            self.assertEqual(path.read_bytes(), before[name])
                        else:
                            self.assertFalse(path.exists())
                self.assertFalse(runtime.exists())
                self.assertFalse(list(root.glob('.perito-runtime-*')))

    def test_production_repeat_disagreement_preserves_uf_but_advances_healthy_national(self):
        self.refresh()
        before = {name: (self.data / name).read_bytes() for name in ('uf.json', 'uf-status.json')}
        evidence = deepcopy(ExportSource(run=7).evidence)
        evidence['snapshot']['qGrandTotalRow'][0]['qNum'] = 1107
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        def zero(root):
            root.find('.//' + ns + 'c[@r="G2"]/' + ns + 'v').text = '0'
        content = workbook_variant(zero)
        for event in evidence['trace']:
            if event.get('state') == 'completed':
                event['receivedBytes'] = event['totalBytes'] = len(content)
        (self.root / 'changed.xlsx').write_bytes(content)
        (self.root / 'changed.json').write_text(json.dumps(evidence))
        env = install_offline_runtime(self.root, [
            {'workbook': str(FIXTURES.resolve() / 'run-6.xlsx'), 'evidence': str(FIXTURES.resolve() / 'run-6.json')},
            {'workbook': str(self.root / 'changed.xlsx'), 'evidence': str(self.root / 'changed.json')},
        ])
        from tests.sources import monthly_resource
        with patch.dict(os.environ, env):
            result = refresh_and_build(self.data, self.site,
                                       source=ControlledArchive(dict([monthly_resource('2026-10')])),
                                       clock=lambda: NOW + timedelta(days=1))
        self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
        self.assertEqual(self.saved('history.json')['observations'][-1]['reference_month'], '2026-10')
        for name, raw in before.items():
            self.assertEqual((self.data / name).read_bytes(), raw)
            self.saved(name)

    def test_live_repeat_denial_cleanup_and_reused_receipt_leave_uf_bytes_but_national_advances(self):
        from tests.sources import monthly_resource
        for case in ('denial', 'cleanup', 'guid'):
            with self.subTest(case=case):
                data, site = self.root / case / 'data', self.root / case / 'site'
                refresh_and_build(data, site, source=ControlledArchive(), uf_source=ExportSource(), clock=lambda: NOW)
                before = {name: (data / name).read_bytes() for name in ('uf.json', 'uf-status.json')}
                evidence = deepcopy(ExportSource(run=7).evidence)
                if case == 'denial':
                    for event in evidence['trace']:
                        if event['kind'] == 'ws_handshake':
                            event['status'] = 403
                elif case == 'guid':
                    guid = next(e['guid'] for e in ExportSource().evidence['trace'] if 'guid' in e)
                    for event in evidence['trace']:
                        if 'guid' in event:
                            event['guid'] = guid
                path = self.root / case / 'second.json'
                path.write_text(json.dumps(evidence))
                second = {'workbook': str(FIXTURES.resolve() / 'run-7.xlsx'), 'evidence': str(path)}
                if case == 'cleanup':
                    second['cleanup'] = {'fatal': None, 'browser_stopped': False, 'clean_profile_removed': False}
                env = install_offline_runtime(self.root / case, [
                    {'workbook': str(FIXTURES.resolve() / 'run-6.xlsx'),
                     'evidence': str(FIXTURES.resolve() / 'run-6.json')}, second])
                sequence = Path(env['PERITO_TEST_EXPORT_SEQUENCE'])
                with patch.dict(os.environ, env):
                    result = refresh_and_build(data, site, source=ControlledArchive(dict([monthly_resource('2026-10')])),
                                               clock=lambda: NOW + timedelta(days=1))
                self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
                for name, raw in before.items():
                    self.assertEqual((data / name).read_bytes(), raw)
                    self.assertEqual((site / 'data' / name).read_bytes(), raw)
                self.assertEqual(json.loads((data / 'history.json').read_text())['observations'][-1]['reference_month'], '2026-10')
                self.assertEqual(sequence.with_suffix('.count').read_text(), '2')
                for line in sequence.with_suffix('.runs').read_text().splitlines():
                    self.assertFalse(Path(json.loads(line)['run']).parent.exists())

    def test_each_healthy_feed_advances_while_failed_feed_bytes_are_preserved(self):
        from tests.sources import monthly_resource
        self.refresh()
        uf_before = {name: (self.data / name).read_bytes() for name in ('uf.json', 'uf-status.json')}
        result = self.refresh(national=ControlledArchive(dict([monthly_resource('2026-10')])), uf=UnavailableUF(), day=1)
        self.assertEqual(result['publication'], 'partial')
        self.assertEqual(self.saved('history.json')['observations'][-1]['reference_month'], '2026-10')
        for name, content in uf_before.items():
            self.assertEqual((self.data / name).read_bytes(), content)
            self.saved(name)
        national_before = {name: (self.data / name).read_bytes() for name in ('history.json', 'status.json')}
        result = self.refresh(national=UnavailableNational(), uf=ExportSource(run=7), day=2)
        self.assertEqual(result['uf'], 'unchanged')
        self.assertEqual(self.saved('uf-status.json')['last_successful_check'], '2026-11-16T12:00:00Z')
        for name, content in national_before.items():
            self.assertEqual((self.data / name).read_bytes(), content)
            self.saved(name)
        self.assertEqual((self.data / 'uf.json').read_bytes(), uf_before['uf.json'])
        self.assertEqual(self.saved('uf-status.json')['last_export']['source']['sha256'],
                         'fbffe323c3485bed0024afe6133f450dc20f51ab8c7aba65a1079be6476e345c')
        self.assertEqual(self.saved('uf.json')['corrections'], [])
        before = self.bytes()
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.refresh(national=UnavailableNational(), uf=UnavailableUF(), day=3)
        self.assertEqual(self.bytes(), before)

    def test_first_uf_failure_keeps_uf_unavailable_not_zero(self):
        result = self.refresh(uf=UnavailableUF())
        self.assertEqual(result, {'national': 'updated', 'uf': 'failed', 'publication': 'partial'})
        self.assertFalse((self.data / 'uf.json').exists())
        self.assertFalse((self.site / 'data/uf-status.json').exists())
        self.assertIn('ausência não é zero', (self.site / 'index.html').read_text())

    def test_explicit_whole_zero_is_distinct_from_missing_pairs_and_correction_is_audited(self):
        self.refresh()
        before = self.saved('uf.json')['current']
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        def zero(root):
            root.find('.//' + ns + 'c[@r="G2"]/' + ns + 'v').text = '0'
        evidence = deepcopy(ExportSource().evidence)
        # G2 is the genuine 1a Cla/AC count of 1, not a generated expected total.
        evidence['snapshot']['qGrandTotalRow'][0]['qNum'] = 1107
        content = workbook_variant(zero)
        national_before = (self.data / 'history.json').read_bytes(), (self.data / 'status.json').read_bytes()
        result = self.refresh(national=UnavailableNational(), uf=ExportSource(content=content, evidence=evidence), day=1)
        self.assertEqual(result, {'national': 'failed', 'uf': 'updated', 'publication': 'partial'})
        self.assertEqual(((self.data / 'history.json').read_bytes(), (self.data / 'status.json').read_bytes()), national_before)
        saved = self.saved('uf.json')
        self.assertEqual(saved['current']['total'], 1107)
        self.assertEqual(saved['current']['counts_by_uf']['AC'], 8)
        self.assertEqual(saved['corrections'][0]['superseded'], before)
        self.assertEqual(len(saved['current']['rows']), 88)
        self.assertIn('0', [r[6] for r in saved['current']['rows']])
        self.refresh(uf=ExportSource(content=content, evidence=evidence), day=2)
        self.assertEqual(self.saved('uf.json'), saved)

    def test_source_explicit_zero_totals_are_valid_without_inference(self):
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        def zero(root):
            for row in root.find(ns + 'sheetData')[1:]:
                row.find(ns + 'c[@r="G' + row.get('r') + '"]/' + ns + 'v').text = '0'
        evidence = deepcopy(ExportSource().evidence)
        evidence['snapshot']['qGrandTotalRow'][0]['qNum'] = 0
        self.refresh(uf=ExportSource(content=workbook_variant(zero), evidence=evidence))
        self.assertEqual(self.saved('uf.json')['current']['total'], 0)
        self.assertEqual(self.saved('uf.json')['current']['counts_by_uf']['DF'], 0)
        self.assertEqual(len(self.saved('uf.json')['current']['rows']), 88)
        self.assertIn('Total: 0 PCFs ativos', (self.site / 'index.html').read_text())

    def test_older_valid_source_period_is_rejected_without_replacing_latest(self):
        self.refresh()
        original = {name: (self.data / name).read_bytes() for name in ('uf.json', 'uf-status.json')}
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        def older(root):
            for row in root.find(ns + 'sheetData')[1:]:
                cell = row.find(ns + 'c[@r="B' + row.get('r') + '"]')
                cell.set('t', 'inlineStr')
                cell[:] = []
                ET.SubElement(ET.SubElement(cell, ns + 'is'), ns + 't').text = 'Ago'
        evidence = deepcopy(ExportSource().evidence)
        evidence['snapshot']['latest'] = {'qText': 'Ago 2026', 'qNum': 46235}
        evidence['snapshot']['availablePeriodCount'] = 1
        evidence['available_periods'] = [{'qText': 'Ago 2026', 'qNum': 46235, 'qState': 'O'}]
        next(s for s in evidence['snapshot']['finalSelections'] if s['label'] == 'Mês/Ano')['selected'] = ['Ago 2026']
        result = self.refresh(uf=ExportSource(content=workbook_variant(older), evidence=evidence), day=1)
        self.assertEqual(result['uf'], 'failed')
        for name, raw in original.items():
            self.assertEqual((self.data / name).read_bytes(), raw)

    def test_missing_runtime_is_blocked_but_a_backward_collection_clock_is_all_fail(self):
        with patch.dict(os.environ, {'PERITO_NODE': '/nonexistent/perito-node'}):
            result = refresh_and_build(self.data, self.site, source=ControlledArchive(), clock=lambda: NOW)
        self.assertEqual(result, {'national': 'updated', 'uf': 'blocked', 'publication': 'partial'})
        before = self.bytes()
        times = iter([NOW + timedelta(days=1), NOW])
        with self.assertRaisesRegex(ValueError, 'Stale'):
            refresh_and_build(self.data, self.site, source=ControlledArchive(), uf_source=ExportSource(), clock=lambda: next(times))
        self.assertEqual(self.bytes(), before)

    def test_invalid_population_coverage_counts_or_evidence_cannot_advance_uf_check(self):
        self.refresh()
        baseline = {name: (self.data / name).read_bytes() for name in ('uf.json', 'uf-status.json')}
        ns = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
        cases = [b'not a workbook']
        for ref, value in [('G2', '-1'), ('G2', '1.5'), ('G2', '*'), ('G2', ''),
                           ('F2', 'XX'), ('E2', 'OUTRO'), ('C2', 'Inativo'), ('D2', 'OUTRO')]:
            def change(root, ref=ref, value=value):
                cell = root.find('.//' + ns + f'c[@r="{ref}"]')
                cell.set('t', 'inlineStr')
                cell[:] = []
                ET.SubElement(ET.SubElement(cell, ns + 'is'), ns + 't').text = value
            cases.append(workbook_variant(change))
        def formula(root):
            ET.SubElement(root.find('.//' + ns + 'c[@r="G2"]'), ns + 'f').text = '1+1'
        cases.append(workbook_variant(formula))
        def missing(root):
            sheet = root.find(ns + 'sheetData')
            sheet.remove(list(sheet)[1])
        cases.append(workbook_variant(missing))
        for content in cases:
            with self.subTest(content=content[:12]):
                result = self.refresh(uf=ExportSource(content=content), day=1)
                self.assertEqual(result['uf'], 'failed')
                for name, raw in baseline.items():
                    self.assertEqual((self.data / name).read_bytes(), raw)
        for change in ('total', 'mapping', 'download', 'period'):
            evidence = deepcopy(ExportSource().evidence)
            if change == 'total':
                evidence['snapshot']['qGrandTotalRow'][0]['qNum'] = 1195
            elif change == 'mapping':
                evidence['snapshot']['mapping']['availableAbbreviations'] = ['OUTRO']
            elif change == 'download':
                next(t for t in evidence['trace'] if t['kind'] == 'Browser.downloadWillBegin')['guid'] = 'unrelated'
            else:
                evidence['snapshot']['finalSelections'][1]['selected'] = ['Out 2026']
            result = self.refresh(uf=ExportSource(evidence=evidence), day=1)
            self.assertEqual(result['uf'], 'failed')
            for name, raw in baseline.items():
                self.assertEqual((self.data / name).read_bytes(), raw)

    def test_corrupt_saved_uf_stale_clock_and_shared_build_failure_preserve_all_outputs(self):
        self.refresh()
        before = self.bytes()
        for filename, value in [('uf.json', {'schema_version': 9}), ('uf-status.json', None)]:
            (self.data / filename).write_text(json.dumps(value))
            corrupt = self.bytes()
            with self.assertRaisesRegex(ValueError, 'saved UF'):
                self.refresh(day=1)
            self.assertEqual(self.bytes(), corrupt)
            for path, raw in before.items():
                (self.root / path).write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.refresh(day=-1)
        self.assertEqual(self.bytes(), before)
        # A real filesystem failure in rendering, not a mock of our renderer.
        blocker = self.root / 'blocked'
        blocker.write_text('not a directory')
        with self.assertRaises((OSError, ValueError)):
            refresh_and_build(self.data, blocker / 'site', source=ControlledArchive(),
                              uf_source=ExportSource(run=7), clock=lambda: NOW + timedelta(days=1))
        self.assertEqual({p: raw for p, raw in self.bytes().items() if p != 'blocked'}, before)

    def test_stale_source_period_is_not_accepted_as_latest(self):
        evidence = deepcopy(ExportSource().evidence)
        evidence['available_periods'].append({'qText': 'Out 2026', 'qNum': 46296, 'qState': 'O'})
        with self.assertRaisesRegex(ValueError, 'latest|period'):
            self.refresh(national=UnavailableNational(), uf=ExportSource(evidence=evidence))
        self.assertEqual(self.bytes(), {})

    def test_first_national_failure_still_publishes_uf_without_inventing_national_check(self):
        result = self.refresh(national=UnavailableNational())
        self.assertEqual(result, {'national': 'failed', 'uf': 'updated', 'publication': 'partial'})
        self.assertFalse((self.data / 'history.json').exists())
        self.assertFalse((self.site / 'data/status.json').exists())
        self.assertEqual(self.saved('uf.json')['current']['total'], 1108)
        html = (self.site / 'index.html').read_text()
        self.assertIn('Verificação nacional indisponível', html)
        self.assertNotIn('href="data/history.json"', html)
        self.assertNotIn('href="data/status.json"', html)
        self.assertIn('1.108 PCFs ativos', html)

    def test_genuine_aggregate_export_reaches_persistence_and_composed_site(self):
        result = self.refresh()
        self.assertEqual(result, {'national': 'updated', 'uf': 'updated', 'publication': 'complete'})
        uf = self.saved('uf.json')
        current = uf['current']
        self.assertEqual(current['reference_month'], '2026-09')
        self.assertEqual(current['total'], 1108)
        self.assertEqual(current['counts_by_uf'], {
            'AC': 9, 'AL': 14, 'AM': 14, 'AP': 7, 'BA': 27, 'CE': 30, 'DF': 324,
            'ES': 21, 'GO': 28, 'MA': 11, 'MG': 79, 'MS': 27, 'MT': 13, 'PA': 13,
            'PB': 25, 'PE': 31, 'PI': 14, 'PR': 71, 'RJ': 55, 'RN': 15, 'RO': 24,
            'RR': 8, 'RS': 57, 'SC': 37, 'SE': 12, 'SP': 130, 'TO': 12})
        self.assertEqual(len(current['rows']), 88)
        self.assertEqual(current['coverage']['absent_class_uf_pairs'], 'not_asserted_zero')
        self.assertEqual(current['geography'], {'source_field': 'UF Servidores', 'meaning': 'UF de lotação',
                                                'basis': 'project_assumption', 'officially_verified': False})
        self.assertEqual(current['scope'], {'organization': 'DPF', 'native_organization': 'Departamento De Policia Federal',
                                           'status': 'Ativo', 'classes': ['Perito Criminal Federal 1a Cla',
                                           'Perito Criminal Federal 2a Cla', 'Perito Criminal Federal 3a Cla',
                                           'Perito Criminal Federal Classe'], 'metric': 'Servidores'})
        self.assertEqual(current['semantic_identity']['version'], 1)
        self.assertEqual(current['source']['url'], 'https://pep.paineis.gov.br/extensions/pep/index.html')
        self.assertEqual(current['source']['app_id'], 'aec332a1-406b-4fec-a776-b1ed66735961')
        self.assertEqual(current['source']['table'], 'Dwnkq')
        self.assertEqual(current['source']['retrieved_at'], '2026-11-14T05:55:38.701Z')
        self.assertEqual(current['source']['filters']['Mês/Ano'], ['Set 2026'])
        self.assertEqual(current['source']['filters']['Orgão'], ['Departamento De Policia Federal'])
        self.assertEqual(current['source']['organization_mapping']['availableAbbreviations'], ['DPF'])
        self.assertEqual(current['source']['anonymous_session'], {'cookie_count_before_navigation': 0, 'websocket_status': 101})
        self.assertEqual(current['source']['sha256'], '5f88f93738b41b035a4bf58450292366afd2aa28b66019c8103e079c0aa6fb55')
        self.assertEqual(self.saved('uf-status.json')['last_successful_check'], '2026-11-14T12:00:00Z')
        html = (self.site / 'index.html').read_text()
        for text in ('Cargos vagos', '1.195', 'Pessoal ativo por UF', 'premissa do projeto', '1.108'):
            self.assertIn(text, html)
