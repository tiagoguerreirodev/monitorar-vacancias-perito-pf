"""Private prospective UF archive. No historical source query capability."""
from copy import deepcopy
import json

from ._uf import _require, _validate_saved_snapshot


def _coverage(observations):
    months = [row['reference_month'] for row in observations]
    available = set(months)
    start, end = months[0], months[-1]
    first_year, first_month = map(int, start.split('-'))
    last_year, last_month = map(int, end.split('-'))
    missing = [f'{index // 12:04d}-{index % 12 + 1:02d}'
               for index in range(first_year * 12 + first_month - 1, last_year * 12 + last_month)
               if f'{index // 12:04d}-{index % 12 + 1:02d}' not in available]
    return {'available_months': months, 'start': start, 'end': end, 'missing_months': missing}


def load_history(data_dir, uf, status, timestamp):
    path = data_dir / 'uf-history.json'
    if not path.exists():
        if uf is None:
            return None
        observations = [deepcopy(uf['current'])]
        return {'schema_version': 1, 'observations': observations,
                'coverage': _coverage(observations), 'corrections': [],
                'legacy_corrections': deepcopy(uf['corrections'])}
    try:
        _require(uf is not None and status is not None, 'saved archive requires UF pair')
        archive = json.loads(path.read_text(encoding='utf-8'))
        _require(set(archive) == {'schema_version', 'observations', 'coverage', 'corrections', 'legacy_corrections'}
                 and type(archive['schema_version']) is int and archive['schema_version'] == 1, 'saved archive schema')
        observations = archive['observations']
        _require(isinstance(observations, list) and bool(observations), 'saved archive observations')
        check = timestamp(status['last_successful_check'])
        for row in observations:
            _validate_saved_snapshot(row, check, timestamp)
        months = [row['reference_month'] for row in observations]
        _require(months == sorted(set(months)), 'saved archive ordered unique months')
        _require(archive['coverage'] == _coverage(observations), 'saved archive coverage')
        _require(observations[-1] == uf['current'], 'saved archive latest mismatch')
        _validate_audits(archive, uf, check, timestamp)
        return archive
    except (OSError, LookupError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid saved UF history: {exc}') from exc


def _validate_audits(archive, uf, check, timestamp):
    canonical = {row['reference_month']: row for row in archive['observations']}
    legacy, transitions = archive['legacy_corrections'], archive['corrections']
    _require(isinstance(legacy, list) and isinstance(transitions, list), 'saved archive audits')
    previous_time = None
    legacy_months = set()
    for audit in legacy:
        _require(set(audit) == {'superseded', 'corrected_at'}, 'saved legacy audit keys')
        row = audit['superseded']
        _validate_saved_snapshot(row, check, timestamp)
        instant = timestamp(audit['corrected_at'])
        _require(row['reference_month'] in canonical and
                 timestamp(row['source']['retrieved_at']) <= instant <= check and
                 (previous_time is None or previous_time <= instant), 'saved legacy audit chronology')
        legacy_months.add(row['reference_month'])
        previous_time = instant
    _require(len(legacy_months) <= 1, 'saved legacy audit month')
    tails = {}
    previous_month = None
    for audit in transitions:
        _require(set(audit) == {'superseded', 'replacement', 'corrected_at'}, 'saved transition keys')
        before, after = audit['superseded'], audit['replacement']
        for row in (before, after):
            _validate_saved_snapshot(row, check, timestamp)
        month = before['reference_month']
        instant = timestamp(audit['corrected_at'])
        _require(month == after['reference_month'] and month in canonical and
                 before['semantic_identity'] != after['semantic_identity'], 'saved transition identity/month')
        _require(all(timestamp(row['source']['retrieved_at']) <= instant <= check for row in (before, after))
                 and (previous_time is None or previous_time <= instant)
                 and (previous_month is None or previous_month <= month), 'saved transition chronology')
        _require(month not in tails or tails[month] == before, 'saved transition chain')
        tails[month] = after
        previous_time, previous_month = instant, month
    _require(all(canonical[month] == tail for month, tail in tails.items()), 'saved transition canonical tail')
    _require(_latest(archive)['corrections'] == uf['corrections'], 'saved latest correction compatibility')


def _latest(archive):
    """Project the compatible latest-only bundle from retained evidence."""
    current = archive['observations'][-1]
    month = current['reference_month']
    corrections = [audit for audit in archive['legacy_corrections']
                   if audit['superseded']['reference_month'] == month]
    corrections += [{'superseded': audit['superseded'], 'corrected_at': audit['corrected_at']}
                    for audit in archive['corrections'] if audit['superseded']['reference_month'] == month]
    return {'schema_version': 1, 'current': current, 'corrections': corrections}


def retain(archive, current, checked_at):
    """Retain original evidence when qualified business facts are unchanged."""
    if archive is None:
        observations = [current]
        return {'schema_version': 1, 'observations': observations,
                'coverage': _coverage(observations), 'corrections': [], 'legacy_corrections': []}
    candidate = deepcopy(archive)
    previous = candidate['observations'][-1]
    if current['reference_month'] < previous['reference_month']:
        raise ValueError('UF source reference month is older than accepted latest')
    if previous['semantic_identity'] == current['semantic_identity']:
        return candidate
    if previous['reference_month'] == current['reference_month']:
        candidate['corrections'].append({'superseded': previous, 'replacement': current,
                                         'corrected_at': checked_at})
        candidate['observations'][-1] = current
    else:
        candidate['observations'].append(current)
    candidate['coverage'] = _coverage(candidate['observations'])
    return candidate
