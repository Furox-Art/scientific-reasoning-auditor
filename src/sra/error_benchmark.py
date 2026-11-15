"""Frozen, bounded structured-check cohorts; no automatically generated truth labels."""
import json
from decimal import Decimal, DecimalException

from sra.document import parse_document_text
from sra.json_utils import reject_duplicate_keys, canonical_json
from sra.toolkit_spec import _fields, _text, _NAME, digest, prepare_toolkit_spec

DECISION_KINDS = frozenset(('polynomial_identity', 'derivative', 'antiderivative',
    'symbolic_identity', 'symbolic_derivative', 'symbolic_antiderivative',
    'unit_conversion', 'statistical_replay', 'statistic_consistency',
    'table_compare', 'causal_graph', 'protocol_consistency'))
LABELS = ('error', 'no_error', 'uncertain', 'not_applicable')


def fingerprint(value):
    return digest(canonical_json(value))


def bounded_json(value, maximum=1024*1024):
    def reject(token):
        raise ValueError('Nonfinite JSON values are forbidden.')
    try:
        raw = value if isinstance(value, str) else canonical_json(value)
        if len(raw) > maximum or len(raw.encode('utf-8')) > maximum:
            raise ValueError('Benchmark JSON exceeds its byte bound.')
        result = json.loads(raw, object_pairs_hook=reject_duplicate_keys, parse_constant=reject, parse_float=Decimal)
    except (TypeError, RecursionError, UnicodeError, DecimalException) as exc:
        raise ValueError('Benchmark inputs must be bounded UTF-8 JSON.') from exc
    if not isinstance(result, dict):
        raise ValueError('Benchmark input must be a JSON object.')
    return result


def records(value, maximum):
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise ValueError('Benchmark record count is outside its bound.')
    result = {}
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not _NAME.fullmatch(row['id']) or row['id'] in result:
            raise ValueError('Benchmark record IDs must be distinct simple identifiers.')
        result[row['id']] = row
    return result


def prepare_manifest(value):
    manifest = bounded_json(value)
    _fields(manifest, ('schema_version', 'dataset_id', 'dataset_kind', 'papers', 'targets', 'cases'))
    _text(manifest['dataset_id'], 200)
    if manifest['schema_version'] != 'error-benchmark/1.0' or manifest['dataset_kind'] not in ('synthetic', 'real_papers'):
        raise ValueError('Unsupported error benchmark schema or dataset kind.')
    papers, targets, cases = (records(manifest[key], bound) for key, bound in
                             (('papers', 32), ('targets', 32), ('cases', 256)))
    documents, groups, sources, hashes, total = {}, {}, {}, set(), 0
    for ident, paper in papers.items():
        _fields(paper, ('id', 'group_id', 'split', 'discipline', 'source_uri', 'license_note', 'text', 'sha256'))
        for key, limit in (('group_id', 100), ('discipline', 100), ('source_uri', 1000), ('license_note', 2000)):
            _text(paper[key], limit)
        if paper['split'] not in ('development', 'test'):
            raise ValueError('Paper split must be development or test.')
        group = paper['group_id'].strip()
        if group in groups and groups[group] != paper['split']:
            raise ValueError('A paper group cannot cross development/test splits.')
        groups[group] = paper['split']
        uri = paper['source_uri'].strip()
        if uri in sources and sources[uri] != group:
            raise ValueError('Repeated declared source URIs must share one paper group.')
        sources[uri] = group
        text = _text(paper['text'], 100000)
        source_hash = digest(text)
        total += len(text)
        if paper['sha256'] != source_hash or source_hash in hashes or total > 200000:
            raise ValueError('Changed/duplicate source snapshot or excessive total text.')
        hashes.add(source_hash)
        documents[ident] = parse_document_text(text, sha256=source_hash, source=ident)
    for target in targets.values():
        _fields(target, ('id', 'kind', 'definition'))
        _text(target['definition'], 2000)
        _text(target['kind'], 100)
    grouped, seen, used = {key: [] for key in papers}, set(), set()
    for case in cases.values():
        _fields(case, ('id', 'paper_id', 'target_id', 'source_quote', 'check'))
        if not isinstance(case['paper_id'], str) or not isinstance(case['target_id'], str) or case['paper_id'] not in papers or case['target_id'] not in targets:
            raise ValueError('Case paper/target reference is absent from the manifest.')
        check = case['check']
        if not isinstance(check, dict) or check.get('id') != case['id'] or check.get('kind') != targets[case['target_id']]['kind']:
            raise ValueError('Case ID/kind must match its structured check and target.')
        quote = _text(case['source_quote'], 2000)
        if quote not in papers[case['paper_id']]['text']:
            raise ValueError('Benchmark quote is absent from the paper snapshot.')
        key = (case['paper_id'], case['target_id'], quote,
               fingerprint({k: v for k, v in check.items() if k != 'id'}))
        if key in seen:
            raise ValueError('Duplicate quoted check would inflate benchmark counts.')
        seen.add(key)
        used.add(case['target_id'])
        grouped[case['paper_id']].append(check)
    if used != set(targets) or any(not checks for checks in grouped.values()):
        raise ValueError('Every paper and target must have at least one case.')
    prepared = {}
    for ident, checks in grouped.items():
        document = documents[ident]
        prepared[ident] = prepare_toolkit_spec(canonical_json({'schema_version': '1.0',
            'source_sha256': document.sha256, 'extracted_text_sha256': digest(document.text),
            'checks': checks}), document)
    return dict(manifest=manifest, manifest_sha256=fingerprint(manifest), papers=papers,
                targets=targets, cases=cases, prepared=prepared)


def decision(kind, status):
    if kind in DECISION_KINDS and status in ('VERIFIED', 'REFUTED'):
        return 'no_error' if status == 'VERIFIED' else 'error'
    return 'abstain'


def run_error_benchmark(value):
    cohort = prepare_manifest(value)
    from sra.toolkit import verify_prepared_toolkit, _numerical_environment
    from sra.provenance import _source_tree_sha256
    results = {}
    for prepared in cohort['prepared'].values():
        for result in verify_prepared_toolkit(prepared)['checks']:
            results[result['id']] = result
    rows = []
    for ident, case in cohort['cases'].items():
        paper, result = cohort['papers'][case['paper_id']], results[ident]
        start = paper['text'].find(case['source_quote'])
        rows.append(dict(id=ident, paper_id=case['paper_id'], target_id=case['target_id'],
                         source_sha256=paper['sha256'], check_sha256=fingerprint(case['check']),
                         source_quote=case['source_quote'], start=start, end=start+len(case['source_quote']),
                         prediction=decision(result['kind'], result['status']), check_result=result))
    tree_hash, _, _ = _source_tree_sha256()
    report = dict(schema_version='error-benchmark-run/1.0',
        manifest_sha256=cohort['manifest_sha256'], dataset_id=cohort['manifest']['dataset_id'],
        dataset_kind=cohort['manifest']['dataset_kind'], mapping_semantics_verified=False,
        execution_status='partial' if any(row['check_result']['status'] in ('FAILED', 'UNAVAILABLE') for row in rows) else 'complete',
        engine={'adapter_version': 'error-benchmark/1.0', 'source_tree_sha256': tree_hash,
                'numerical_environment': _numerical_environment()}, cases=rows,
        limitations=['Decisions concern explicitly supplied structured checks, not manuscript truth.',
                     'Caller prose-to-check mappings and source authenticity are not verified.',
                     'All nondecisive or unsupported check statuses abstain; no candidate is a negative label.'])
    report['report_sha256'] = fingerprint(report)
    bounded_json(report, 4*1024*1024)
    return report


def error_label_template(value):
    cohort = prepare_manifest(value)
    return dict(schema_version='error-labels/1.0', manifest_sha256=cohort['manifest_sha256'],
                label_origin='synthetic_fixture' if cohort['manifest']['dataset_kind'] == 'synthetic' else 'caller_declared_external',
                cases=[{'id': ident, 'reviewers': [{'reviewer_id': None, 'label': None, 'rationale': ''} for _ in range(2)],
                        'adjudication': None} for ident in cohort['cases']])
