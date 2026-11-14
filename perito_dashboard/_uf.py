"""Public-aggregate UF document boundary; no individual personnel data."""
from dataclasses import dataclass
from datetime import datetime
import hashlib
from io import BytesIO
import json
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

ENTRY = 'https://pep.paineis.gov.br/extensions/pep/index.html'
APP = 'aec332a1-406b-4fec-a776-b1ed66735961'
CARGOS = ['Perito Criminal Federal 1a Cla', 'Perito Criminal Federal 2a Cla',
          'Perito Criminal Federal 3a Cla', 'Perito Criminal Federal Classe']
UFS = sorted('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())
HEADERS = ['Ano', 'Mês', 'Grupo Situação do Vínculo', 'Nome do Cargo', 'Orgão', 'UF', 'Servidores']
MONTHS = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
GEOGRAPHY = {'source_field': 'UF Servidores', 'meaning': 'UF de lotação',
             'basis': 'project_assumption', 'officially_verified': False}
COVERAGE = {'ufs': UFS, 'absent_class_uf_pairs': 'not_asserted_zero'}
SCOPE = {'organization': 'DPF', 'native_organization': 'Departamento De Policia Federal',
         'status': 'Ativo', 'classes': CARGOS, 'metric': 'Servidores'}


@dataclass(frozen=True)
class UFExport:
    """New workbook bytes and same-run ordinary-frontend selection/download evidence."""
    content: bytes
    evidence: dict


def _require(condition, message):
    if not condition:
        raise ValueError('Invalid UF export: ' + message)


def _xml(archive, name):
    content = archive.read(name)
    _require(b'<!DOCTYPE' not in content.upper() and b'<!ENTITY' not in content.upper(), 'XML declarations')
    return ET.fromstring(content)


def _rows(content):
    _require(isinstance(content, bytes) and len(content) <= 2_000_000, 'workbook size/type')
    with ZipFile(BytesIO(content)) as archive:
        members = archive.infolist()
        _require(len(members) <= 40 and len({i.filename for i in members}) == len(members), 'ZIP members')
        _require(sum(i.file_size for i in members) <= 8_000_000, 'expanded ZIP size')
        _require(all(not i.flag_bits & 1 and not i.filename.startswith('/') and '..' not in i.filename.split('/')
                     for i in members), 'ZIP paths/encryption')
        _require(archive.testzip() is None, 'ZIP integrity')
        allowed = {'[Content_Types].xml', '_rels/.rels', 'xl/_rels/workbook.xml.rels',
                   'xl/worksheets/sheet1.xml', 'xl/workbook.xml', 'xl/sharedStrings.xml',
                   'xl/theme/theme1.xml', 'xl/styles.xml', 'docProps/core.xml', 'docProps/app.xml'}
        _require(set(archive.namelist()) <= allowed, 'unexpected package parts')
        for name in ('_rels/.rels', 'xl/_rels/workbook.xml.rels'):
            relationships = _xml(archive, name)
            _require(all(r.get('TargetMode') != 'External' and not re.match(r'[a-zA-Z]+:', r.get('Target', ''))
                         and '..' not in r.get('Target', '').split('/') for r in relationships), 'external package relationship')
        workbook = _xml(archive, 'xl/workbook.xml')
        sheet = workbook.find(NS + 'sheets/' + NS + 'sheet')
        relation_id = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id') if sheet is not None else None
        _require(any(r.get('Id') == relation_id and r.get('Target') == 'worksheets/sheet1.xml'
                     and r.get('Type', '').endswith('/worksheet') for r in relationships), 'worksheet relationship')
        _require(len(workbook.findall(NS + 'sheets/' + NS + 'sheet')) == 1, 'one worksheet required')
        sheets = [i.filename for i in members if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', i.filename)]
        _require(len(sheets) == 1, 'one worksheet required')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(s.itertext()) for s in _xml(archive, 'xl/sharedStrings.xml').findall(NS + 'si')]
            _require(len(strings) <= 1000 and all(len(s) < 300 for s in strings), 'shared strings bound')
        result = []
        for index, row in enumerate(_xml(archive, sheets[0]).findall(NS + 'sheetData/' + NS + 'row'), 1):
            _require(index <= 109 and row.get('r') == str(index), 'row range/order')
            cells = row.findall(NS + 'c')
            _require(len(cells) == 7, 'seven explicit cells required')
            values = []
            for column, cell in zip('ABCDEFG', cells):
                _require(cell.get('r') == column + str(index), 'cell range/order')
                _require(cell.find(NS + 'f') is None, 'formula not allowed')
                kind = cell.get('t', 'n')
                _require(kind in ('s', 'n', 'inlineStr'), 'cell type/error')
                value = cell.findtext(NS + 'v')
                if kind == 's':
                    _require(value is not None and re.fullmatch(r'\d+', value) is not None and int(value) < len(strings), 'string reference')
                    value = strings[int(value)]
                elif kind == 'inlineStr':
                    value = ''.join(cell.find(NS + 'is').itertext()) if cell.find(NS + 'is') is not None else ''
                _require(isinstance(value, str) and len(value) < 300, 'missing/oversize cell')
                values.append(value)
            result.append(values)
    _require(bool(result) and result[0] == HEADERS, 'exact headers')
    return result[1:]


def _aggregate(rows):
    _require(isinstance(rows, list) and 1 <= len(rows) <= 108, 'row count')
    _require(all(isinstance(r, list) and len(r) == 7 and all(isinstance(v, str) for v in r) for r in rows), 'row schema')
    _require(len({tuple(r[:6]) for r in rows}) == len(rows), 'duplicate class-UF groups')
    periods = {tuple(r[:2]) for r in rows}
    _require(len(periods) == 1, 'single period')
    year, month = next(iter(periods))
    _require(re.fullmatch(r'[0-9]{4}', year) is not None and int(year) > 0 and month in MONTHS, 'reference month')
    _require({r[2] for r in rows} == {'Ativo'} and {r[3] for r in rows} == set(CARGOS)
             and {r[4] for r in rows} == {'DPF'} and {r[5] for r in rows} == set(UFS), 'population/UF coverage')
    _require(all(re.fullmatch(r'0|[1-9][0-9]{0,8}', r[6]) is not None for r in rows), 'whole nonnegative explicit counts')
    counts = {uf: sum(int(r[6]) for r in rows if r[5] == uf) for uf in UFS}
    identity = {'version': 1, 'rows': sorted(rows), 'scope': SCOPE, 'geography': GEOGRAPHY, 'coverage': COVERAGE}
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return {'reference_month': f'{year}-{MONTHS.index(month) + 1:02d}', 'rows': sorted(rows),
            'counts_by_uf': counts, 'total': sum(counts.values()), 'scope': SCOPE,
            'coverage': COVERAGE, 'geography': GEOGRAPHY,
            'semantic_identity': {'version': 1, 'sha256': hashlib.sha256(canonical).hexdigest()}}


def _evidence(evidence, current, checked_at, content_size):
    snapshot, trace = evidence['snapshot'], evidence['trace']
    _require(snapshot['entry'] == ENTRY + '#fvm' and snapshot['appId'] == APP and snapshot['table'] == 'Dwnkq', 'entry/app/table')
    mapping = snapshot['mapping']
    _require(mapping['nativeOrgaoField'] == 'Órgão (Servidores)'
             and mapping['nativePfLabel'] == SCOPE['native_organization']
             and mapping['physicalFields'] == ['Sigla Orgão Vinculado (Servidores)']
             and mapping['availableAbbreviations'] == ['DPF'], 'native organization mapping')
    expected = {'Seção': ['Servidores'], 'Mês/Ano': [snapshot['latest']['qText']],
                'Grupo Situação do Vinculo': ['Ativo'], 'Orgão': [SCOPE['native_organization']],
                'Cargo': CARGOS, 'Dimensão': HEADERS[2:6], 'Métricas': ['Servidores']}
    selections = snapshot['finalSelections']
    _require(len(selections) == len(expected) and {s['label'] for s in selections} == set(expected), 'selection labels')
    _require(all(sorted(s['selected']) == sorted(expected[s['label']]) for s in selections), 'actual selections')
    year, month = current['reference_month'].split('-')
    eligible = [p for p in evidence['available_periods'] if p['qState'] in ('O', 'A', 'S')
                and type(p.get('qNum')) in (int, float) and -1e8 < p['qNum'] < 1e8]
    _require(bool(eligible) and len(eligible) == snapshot['availablePeriodCount']
             and snapshot['latest']['qNum'] == max(p['qNum'] for p in eligible)
             and any(p['qNum'] == snapshot['latest']['qNum'] and p['qText'] == snapshot['latest']['qText'] for p in eligible), 'latest eligible period')
    _require(snapshot['latest']['qText'] == MONTHS[int(month)-1] + ' ' + year
             and snapshot['latest']['qNum'] == (datetime(int(year), int(month), 1) - datetime(1899, 12, 30)).days,
             'selected period')
    _require(snapshot['qSize'] == {'qcx': 7, 'qcy': len(current['rows'])}
             and sorted(snapshot['dimensions']) == sorted(HEADERS[:6]), 'layout dimensions/rows')
    totals = snapshot['qGrandTotalRow']
    _require(len(totals) == 1 and type(totals[0]['qNum']) in (int, float)
             and totals[0]['qNum'] == current['total'], 'own-source total reconciliation')
    _require([m['title'] for m in snapshot['measure']] == ['Servidores'], 'measure')
    isolated = [t for t in trace if t['kind'] == 'isolation']
    started = [t for t in trace if t['kind'] == 'Browser.downloadWillBegin']
    completed = [t for t in trace if t['kind'] == 'Browser.downloadProgress' and t['state'] == 'completed']
    _require(len(isolated) == 1 and type(isolated[0]['cookieCountBeforeNavigation']) is int
             and isolated[0]['cookieCountBeforeNavigation'] == 0, 'clean anonymous session')
    _require(any(t['kind'] == 'ws_handshake' and t['status'] == 101 for t in trace), 'ordinary frontend handshake')
    _require(not any(t['kind'] == 'STOP' or (t.get('status') in (401, 403, 429)) for t in trace), 'source denial')
    _require(len(started) == len(completed) == 1 and started[0]['guid'] == completed[0]['guid']
             and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', started[0]['guid']) is not None,
             'fresh correlated download')
    _require(started[0]['url'].startswith('https://pep.paineis.gov.br/tempcontent/')
             and type(completed[0]['receivedBytes']) is int and type(completed[0]['totalBytes']) is int
             and completed[0]['receivedBytes'] == completed[0]['totalBytes'] == content_size > 0, 'download completion')
    times = [isolated[0]['utc'], snapshot['utc'], started[0]['utc'], completed[0]['utc'], checked_at]
    instants = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in times]
    _require(all(t.utcoffset() is not None for t in instants) and instants == sorted(instants), 'retrieval chronology')
    return {'url': ENTRY, 'app_id': APP, 'table': 'Dwnkq', 'retrieved_at': completed[0]['utc'],
            'download_guid': started[0]['guid'], 'own_source_total': current['total'],
            'filters': {s['label']: s['selected'] for s in selections},
            'organization_mapping': {key: mapping[key] for key in
                                     ('nativeOrgaoField', 'nativePfLabel', 'physicalFields', 'availableAbbreviations')},
            'anonymous_session': {'cookie_count_before_navigation': 0, 'websocket_status': 101},
            'evidence_sha256': hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False,
                                                       separators=(',', ':')).encode()).hexdigest()}


def accept_export(export, checked_at):
    try:
        current = _aggregate(_rows(export.content))
        source = _evidence(export.evidence, current, checked_at, len(export.content))
        source['sha256'] = hashlib.sha256(export.content).hexdigest()
        current['source'] = source
        return current
    except (KeyError, TypeError, AttributeError, IndexError, BadZipFile, ET.ParseError, OverflowError, NotImplementedError) as exc:
        raise ValueError(f'Invalid UF export: {type(exc).__name__}') from exc


def load_saved(data_dir, timestamp):
    paths = [data_dir / 'uf.json', data_dir / 'uf-status.json']
    if not any(p.exists() for p in paths):
        return None, None
    try:
        data, status = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
        _require(set(data) == {'schema_version', 'current', 'corrections'}
                 and set(status) == {'schema_version', 'last_successful_check', 'last_export'}, 'saved document keys')
        _require(type(data['schema_version']) is int and data['schema_version'] == 1
                 and type(status['schema_version']) is int and status['schema_version'] == 1, 'saved schema')
        check = timestamp(status['last_successful_check'])
        def validate(current):
            aggregate = _aggregate(current['rows'])
            _require(set(current) == set(aggregate) | {'source'} and
                     json.dumps({k: current[k] for k in aggregate}, sort_keys=True) == json.dumps(aggregate, sort_keys=True), 'saved aggregate identity')
            source = current['source']
            _require(set(source) == {'url', 'app_id', 'table', 'retrieved_at', 'download_guid', 'own_source_total', 'sha256', 'evidence_sha256',
                                             'filters', 'organization_mapping', 'anonymous_session'}
                     and source['url'] == ENTRY and source['app_id'] == APP and source['table'] == 'Dwnkq'
                     and re.fullmatch('[0-9a-f]{64}', source['evidence_sha256']) is not None
                     and type(source['own_source_total']) is int and source['own_source_total'] == current['total']
                     and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', source['download_guid']) is not None
                     and re.fullmatch('[0-9a-f]{64}', source['sha256']) is not None
                     and timestamp(source['retrieved_at']) <= check, 'saved source provenance')
            year, month = current['reference_month'].split('-')
            _require(source['filters'] == {'Seção': ['Servidores'], 'Mês/Ano': [MONTHS[int(month)-1] + ' ' + year],
                                          'Grupo Situação do Vinculo': ['Ativo'], 'Orgão': [SCOPE['native_organization']],
                                          'Cargo': CARGOS, 'Dimensão': HEADERS[2:6], 'Métricas': ['Servidores']}
                     and source['organization_mapping'] == {'nativeOrgaoField': 'Órgão (Servidores)',
                                                            'nativePfLabel': SCOPE['native_organization'],
                                                            'physicalFields': ['Sigla Orgão Vinculado (Servidores)'],
                                                            'availableAbbreviations': ['DPF']}
                     and json.dumps(source['anonymous_session'], sort_keys=True) ==
                         '{"cookie_count_before_navigation": 0, "websocket_status": 101}', 'saved source outcomes')
        validate(data['current'])
        _require(isinstance(data['corrections'], list), 'saved corrections')
        for correction in data['corrections']:
            validate(correction['superseded'])
            _require(correction['superseded']['reference_month'] == data['current']['reference_month']
                     and timestamp(correction['corrected_at']) <= check, 'saved correction audit')
        validate(status['last_export'])
        _require(status['last_export']['semantic_identity'] == data['current']['semantic_identity'], 'saved status identity')
        return data, status
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid saved UF data: {exc}') from exc
