"""Dependency-free preflight for bounded, caller-supplied evidence snapshots."""
import json
import re

EVIDENCE_KINDS = ('source_overlap', 'protocol_consistency', 'checklist_evidence')


def tokens(text):
    """Unicode word runs; casefold for comparison, retain original codepoint offsets."""
    return [(match.group().casefold(), match.start(), match.end())
            for match in re.finditer(r'\w+', text)]


def _rows(value, minimum=1):
    if not isinstance(value, list) or not minimum <= len(value) <= 100:
        raise ValueError('Supply a bounded list of distinct evidence records.')
    return value


def _identifier(row, seen):
    from sra.toolkit_spec import _NAME
    if not isinstance(row.get('id'), str) or not _NAME.fullmatch(row['id']) or row['id'] in seen:
        raise ValueError('Evidence IDs must be distinct simple identifiers.')
    seen.add(row['id'])


def _snapshot(value):
    from sra.toolkit_spec import _fields, _text, digest
    _fields(value, ('text', 'sha256'))
    text = _text(value['text'], 100000)
    if digest(text) != value['sha256']:
        raise ValueError('Evidence snapshot hash mismatch.')
    return text


def _quote(value, text):
    from sra.document import SourceIdentityError
    from sra.toolkit_spec import _text
    quote = _text(value, 2000)
    start = text.find(quote)
    if start < 0:
        raise SourceIdentityError('Evidence quote is absent from its declared snapshot.')
    return {'quote': quote, 'start': start, 'end': start + len(quote)}


def prepare_evidence(item, document):
    from sra.toolkit_spec import _fields, _text, digest
    kind = item['kind']
    required = {'source_overlap': ('sources',), 'protocol_consistency': ('protocol', 'fields'),
                'checklist_evidence': ('checklist', 'assessments')}[kind]
    _fields(item, ('id', 'kind') + required,
            ('text', 'min_tokens') if kind == 'source_overlap' else ('text',))
    if document is not None and 'text' in item:
        raise ValueError('Bound evidence checks use manuscript text; alternate text is forbidden.')
    text = _text(document.text if document is not None else item.get('text'), 100000)
    result = dict(item, text=text, text_sha256=digest(text))
    if kind == 'source_overlap':
        size = item.get('min_tokens', 8)
        if type(size) is not int or not 5 <= size <= 20:
            raise ValueError('min_tokens must be an integer in [5,20].')
        sources = item['sources']
        if not isinstance(sources, list) or not 1 <= len(sources) <= 8:
            raise ValueError('Supply 1..8 comparison sources.')
        seen, total = set(), len(text)
        result.update(min_tokens=size, manuscript_tokens=tokens(text))
        prepared = []
        for row in sources:
            _fields(row, ('id', 'text', 'sha256'))
            _identifier(row, seen)
            source = _snapshot({key: row[key] for key in ('text', 'sha256')})
            total += len(source)
            prepared.append(dict(row, tokens=tokens(source)))
        if total > 200000 or any(len(row['tokens']) > 20000 for row in prepared) or len(result['manuscript_tokens']) > 20000:
            raise ValueError('Overlap exceeds 200000 total characters or 20000 tokens per snapshot.')
        result['sources'] = prepared
    elif kind == 'protocol_consistency':
        protocol = _snapshot(item['protocol'])
        seen, fields = set(), []
        for row in _rows(item['fields']):
            _fields(row, ('id', 'protocol', 'manuscript'))
            _identifier(row, seen)
            mapped = {'id': row['id']}
            for key, source in (('protocol', protocol), ('manuscript', text)):
                value = row[key]
                if value is not None:
                    _fields(value, ('value', 'quote'))
                    value = dict(value=_text(value['value'], 2000), **_quote(value['quote'], source))
                mapped[key] = value
            fields.append(mapped)
        result['fields'] = fields
    else:
        checklist = item['checklist']
        _fields(checklist, ('name', 'version', 'items'))
        _text(checklist['name'], 200)
        _text(checklist['version'], 100)
        seen = set()
        for row in _rows(checklist['items']):
            _fields(row, ('id', 'requirement'))
            _identifier(row, seen)
            _text(row['requirement'], 2000)
        result['checklist_sha256'] = digest(json.dumps(checklist, sort_keys=True, ensure_ascii=False))
        assessed, assessments = set(), []
        for row in _rows(item['assessments'], 0):
            if not isinstance(row, dict) or not isinstance(row.get('status'), str) or row['status'] not in ('reported', 'not_applicable', 'unknown'):
                raise ValueError('Checklist status must be reported, not_applicable or unknown.')
            status = row['status']
            _fields(row, ('id', 'status') + (('quote',) if status == 'reported' else
                    ('rationale',) if status == 'not_applicable' else ()))
            _identifier(row, assessed)
            if row['id'] not in seen:
                raise ValueError('Assessment ID is absent from the supplied checklist.')
            record = dict(row)
            if status == 'reported':
                record.update(_quote(row['quote'], text))
            elif status == 'not_applicable':
                _text(row['rationale'], 2000)
            assessments.append(record)
        result['assessments'] = assessments
    return result
