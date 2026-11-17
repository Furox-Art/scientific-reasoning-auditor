"""Bounded preflight for record audits and declared measurement comparisons."""
from datetime import date

from sra.evidence_spec import _identifier, _quote, _rows, _snapshot

METHOD_AUDIT_KINDS = ('novelty_comparison', 'literature_search_audit',
                      'measurement_agreement', 'question_method_alignment')
TARGET_FIELDS = ('population', 'outcome', 'contrast', 'timepoint', 'effect_measure', 'analysis_unit')


def _date(value):
    if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Dates require ISO YYYY-MM-DD notation.')
    return value


def _count(value):
    if type(value) is not int or not 0 <= value <= 100000000:
        raise ValueError('Counts require integers in [0,100000000].')
    return value


def _mapping(value, fields, text):
    from sra.toolkit_spec import _fields, _text
    _fields(value, fields)
    mapped = {}
    for field in fields:
        row = value[field]
        if row is not None:
            _fields(row, ('value', 'quote'))
            row = dict(value=_text(row['value'], 2000), **_quote(row['quote'], text))
            if row['value'] not in row['quote']:
                raise ValueError('Mapped values must occur literally in their evidence quotes.')
        mapped[field] = row
    return mapped


def prepare_method_audit(item, document):
    from sra.toolkit_spec import _fields, _text, _NAME, digest, number
    kind = item['kind']
    required = {
        'novelty_comparison': ('dimensions', 'contribution', 'comparators'),
        'literature_search_audit': ('required_sources', 'searches', 'as_of', 'max_age_days', 'deduplication'),
        'measurement_agreement': ('reference', 'measured', 'unit', 'independent_pairs',
                                  'normal_differences', 'constant_bias_and_variance', 'acceptable_difference'),
        'question_method_alignment': ('question', 'method'),
    }[kind]
    textual = kind in ('novelty_comparison', 'question_method_alignment')
    _fields(item, ('id', 'kind') + required, ('text',) if textual else ())
    result = dict(item)
    if textual:
        if document is not None and 'text' in item:
            raise ValueError('Bound method audits use manuscript text; alternate text is forbidden.')
        text = _text(document.text if document is not None else item.get('text'), 100000)
        result.update(text=text, text_sha256=digest(text))
    if kind == 'question_method_alignment':
        result['question'] = _mapping(item['question'], TARGET_FIELDS, text)
        result['method'] = _mapping(item['method'], TARGET_FIELDS, text)
    elif kind == 'novelty_comparison':
        dimensions = item['dimensions']
        if (not isinstance(dimensions, list) or not 1 <= len(dimensions) <= 16 or
                any(not isinstance(key, str) or not _NAME.fullmatch(key) for key in dimensions) or
                len(set(dimensions)) != len(dimensions)):
            raise ValueError('Declare 1..16 distinct simple dimension identifiers.')
        result['contribution'] = _mapping(item['contribution'], dimensions, text)
        prepared, seen, total = [], set(), len(text)
        for row in _rows(item['comparators']):
            _fields(row, ('id', 'text', 'sha256', 'features'))
            _identifier(row, seen)
            snapshot = _snapshot({key: row[key] for key in ('text', 'sha256')})
            total += len(snapshot)
            prepared.append(dict(row, features=_mapping(row['features'], dimensions, snapshot)))
        if total > 200000:
            raise ValueError('Comparison snapshots exceed 200000 total characters.')
        result['comparators'] = prepared
    elif kind == 'literature_search_audit':
        required_sources = item['required_sources']
        if (not isinstance(required_sources, list) or not 1 <= len(required_sources) <= 32 or
                any(not isinstance(key, str) or not _NAME.fullmatch(key) for key in required_sources) or
                len(set(required_sources)) != len(required_sources)):
            raise ValueError('Declare 1..32 distinct required source identifiers.')
        _date(item['as_of'])
        if type(item['max_age_days']) is not int or not 0 <= item['max_age_days'] <= 36500:
            raise ValueError('Caller-selected search age must be in [0,36500] days.')
        seen = set()
        for row in _rows(item['searches'], 0):
            _fields(row, ('id', 'source', 'platform', 'query', 'searched_on',
                          'coverage_start', 'coverage_end', 'records_found'))
            _identifier(row, seen)
            if not isinstance(row['source'], str) or not _NAME.fullmatch(row['source']):
                raise ValueError('Search source must be a simple identifier.')
            for key in ('platform', 'query'):
                if row[key] is not None:
                    _text(row[key], 4000)
            for key in ('searched_on', 'coverage_start', 'coverage_end'):
                if row[key] is not None:
                    _date(row[key])
            if row['records_found'] is not None:
                _count(row['records_found'])
        counts = item['deduplication']
        _fields(counts, ('records_before', 'duplicates_removed', 'records_after'))
        for value in counts.values():
            if value is not None:
                _count(value)
    else:
        reference, measured = item['reference'], item['measured']
        if (not isinstance(reference, list) or not isinstance(measured, list) or
                len(reference) != len(measured) or not 3 <= len(reference) <= 1000):
            raise ValueError('Measurement agreement needs 3..1000 one-to-one pairs.')
        for key in ('reference', 'measured'):
            values = [number(value) for value in item[key]]
            if any(value.copy_abs() > number('1e12') for value in values):
                raise ValueError('Measurement magnitudes must not exceed 1e12.')
            result[key] = [format(value, 'f') for value in values]
        _text(item['unit'], 100)
        for key in ('independent_pairs', 'normal_differences', 'constant_bias_and_variance'):
            if item[key] is not None and type(item[key]) is not bool:
                raise ValueError('Measurement assumptions must be booleans or null.')
        band = item['acceptable_difference']
        if band is not None:
            _fields(band, ('lower', 'upper'))
            low, high = number(band['lower']), number(band['upper'])
            if not number('1e12').copy_negate() <= low < high <= number('1e12'):
                raise ValueError('Acceptable difference needs ordered bounds within +/-1e12.')
            result['acceptable_difference'] = dict(lower=format(low, 'f'), upper=format(high, 'f'))
    return result
