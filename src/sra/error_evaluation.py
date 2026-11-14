"""Conditional cohort comparisons with explicit abstention and exclusion denominators."""
from sra.error_benchmark import (LABELS, bounded_json, decision,
                                 fingerprint, prepare_manifest, records)
from sra.toolkit_spec import _fields, _text, _NAME, _HASH


def _reviewer(value):
    _fields(value, ('reviewer_id', 'label', 'rationale'))
    ident = value['reviewer_id']
    if not isinstance(ident, str) or not _NAME.fullmatch(ident) or value['label'] not in LABELS or len(_text(value['rationale'], 2000).strip()) < 20:
        raise ValueError('Review needs a distinct ID, supported label and 20-character rationale.')
    return ident, value['label']


def _gold(cohort, value):
    labels = bounded_json(value)
    _fields(labels, ('schema_version', 'manifest_sha256', 'label_origin', 'cases'))
    expected_origin = 'synthetic_fixture' if cohort['manifest']['dataset_kind'] == 'synthetic' else 'caller_declared_external'
    if labels['schema_version'] != 'error-labels/1.0' or labels['manifest_sha256'] != cohort['manifest_sha256'] or labels['label_origin'] != expected_origin:
        raise ValueError('Label schema, manifest or declared origin does not match.')
    entries = records(labels['cases'], 256)
    if set(entries) != set(cohort['cases']):
        raise ValueError('Every benchmark case, including negatives, needs exactly one label record.')
    result, agreements = {}, 0
    for ident, row in entries.items():
        _fields(row, ('id', 'reviewers', 'adjudication'))
        reviewers = row['reviewers']
        if not isinstance(reviewers, list) or len(reviewers) != 2:
            raise ValueError('Every case requires two declared reviewers.')
        left, right = [_reviewer(reviewer) for reviewer in reviewers]
        if left[0] == right[0]:
            raise ValueError('Reviewer IDs must be distinct.')
        agreed = left[1] == right[1]
        agreements += agreed
        if row['adjudication'] is not None:
            third = _reviewer(row['adjudication'])
            if third[0] in (left[0], right[0]):
                raise ValueError('Adjudicator must differ from the two reviewers.')
            result[ident] = third[1]
        elif agreed:
            result[ident] = left[1]
        else:
            raise ValueError('Disagreement requires an explicit third-party adjudication.')
    return labels, result, agreements


def _predictions(cohort, value):
    run = bounded_json(value, 4*1024*1024)
    _fields(run, ('schema_version', 'manifest_sha256', 'dataset_id', 'dataset_kind', 'mapping_semantics_verified',
                  'execution_status', 'engine', 'cases', 'limitations', 'report_sha256'))
    if run['report_sha256'] != fingerprint({k:v for k,v in run.items() if k != 'report_sha256'}):
        raise ValueError('Imported run fingerprint does not match its contents.')
    if (run['schema_version'] != 'error-benchmark-run/1.0' or run['manifest_sha256'] != cohort['manifest_sha256'] or
            run['dataset_id'] != cohort['manifest']['dataset_id'] or run['dataset_kind'] != cohort['manifest']['dataset_kind'] or
            run['mapping_semantics_verified'] is not False or run['execution_status'] not in ('complete', 'partial')):
        raise ValueError('Run contract or manifest identity differs.')
    entries = records(run['cases'], 256)
    engine = run['engine']
    _fields(engine, ('adapter_version', 'source_tree_sha256', 'numerical_environment'))
    if (engine['adapter_version'] != 'error-benchmark/1.0' or
            (engine['source_tree_sha256'] is not None and
             (not isinstance(engine['source_tree_sha256'], str) or not _HASH.fullmatch(engine['source_tree_sha256']))) or
            not isinstance(engine['numerical_environment'], dict)):
        raise ValueError('Run engine metadata is malformed.')
    if set(entries) != set(cohort['cases']):
        raise ValueError('Frozen predictions must cover every benchmark case exactly once.')
    for ident, row in entries.items():
        _fields(row, ('id', 'paper_id', 'target_id', 'source_sha256', 'check_sha256', 'source_quote', 'start', 'end', 'prediction', 'check_result'))
        case = cohort['cases'][ident]
        paper = cohort['papers'][case['paper_id']]
        start = paper['text'].find(case['source_quote'])
        if (row['paper_id'] != case['paper_id'] or row['target_id'] != case['target_id'] or
                row['source_sha256'] != paper['sha256'] or row['check_sha256'] != fingerprint(case['check']) or
                row['source_quote'] != case['source_quote'] or type(row['start']) is not int or type(row['end']) is not int or
                row['start'] != start or row['end'] != start + len(case['source_quote'])):
            raise ValueError('Prediction source, check mapping or quoted offsets changed.')
        check = row['check_result']
        _fields(check, ('id', 'kind', 'backend', 'backend_version', 'status', 'details'))
        _text(check['backend'], 100)
        if check['backend_version'] is not None:
            _text(check['backend_version'], 100)
        if (check['id'] != ident or check['kind'] != case['check']['kind'] or
                check['status'] not in ('VERIFIED', 'REFUTED', 'CANDIDATES', 'CALCULATED', 'UNDETERMINED', 'UNAVAILABLE', 'FAILED') or
                not isinstance(check['details'], dict) or row['prediction'] != decision(check['kind'], check['status'])):
            raise ValueError('Prediction does not follow the retained structured-check decision.')
    expected_status = 'partial' if any(row['check_result']['status'] in ('FAILED', 'UNAVAILABLE') for row in entries.values()) else 'complete'
    if run['execution_status'] != expected_status:
        raise ValueError('Run execution status contradicts individual backend outcomes.')
    return run, entries


def _ratio(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                value=numerator/denominator if denominator else None)


def _summary(rows):
    counts = dict.fromkeys(('tp', 'fp', 'fn', 'tn'), 0)
    excluded = dict.fromkeys(('uncertain', 'not_applicable'), 0)
    abstentions = dict.fromkeys(('error', 'no_error'), 0)
    for row in rows:
        truth, predicted = row['gold'], row['prediction']
        if truth in excluded:
            excluded[truth] += 1
        elif predicted == 'abstain':
            abstentions[truth] += 1
        else:
            key = ('tp' if truth == 'error' else 'fp') if predicted == 'error' else ('fn' if truth == 'error' else 'tn')
            counts[key] += 1
    tp, fp, fn, tn = (counts[k] for k in ('tp', 'fp', 'fn', 'tn'))
    decided = sum(counts.values())
    eligible = decided + sum(abstentions.values())
    return dict(total_cases=len(rows), binary_labeled_cases=eligible, confusion=counts,
                excluded=excluded, abstentions=abstentions, metrics={
                    'decision_coverage': _ratio(decided, eligible),
                    'selective_accuracy': _ratio(tp+tn, decided),
                    'selective_risk': _ratio(fp+fn, decided),
                    'decided_precision': _ratio(tp, tp+fp),
                    'decided_recall': _ratio(tp, tp+fn),
                    'decided_specificity': _ratio(tn, tn+fp),
                    'decided_false_positive_rate': _ratio(fp, fp+tn),
                    'end_to_end_recall': _ratio(tp, tp+fn+abstentions['error']),
                    'false_alarms_per_labeled_negative': _ratio(fp, fp+tn+abstentions['no_error'])})


def evaluate_errors(manifest, predictions, labels):
    cohort = prepare_manifest(manifest)
    run, predicted = _predictions(cohort, predictions)
    label_file, gold, agreements = _gold(cohort, labels)
    rows = []
    for ident, case in cohort['cases'].items():
        paper = cohort['papers'][case['paper_id']]
        rows.append(dict(id=ident, paper_id=case['paper_id'], target_id=case['target_id'],
                         discipline=paper['discipline'], split=paper['split'],
                         source_sha256=paper['sha256'], gold=gold[ident],
                         prediction=predicted[ident]['prediction'], check_status=predicted[ident]['check_result']['status']))
    report = dict(schema_version='error-evaluation/1.0', execution_status='complete',
                  dataset_id=cohort['manifest']['dataset_id'], dataset_kind=cohort['manifest']['dataset_kind'],
                  manifest_sha256=cohort['manifest_sha256'], predictions_sha256=run['report_sha256'],
                  labels_sha256=fingerprint(label_file), label_origin=label_file['label_origin'],
                  reviewer_identity_verified=False, reviewer_agreement=_ratio(agreements, len(rows)),
                  paper_count=len(cohort['papers']), group_count=len({p['group_id'].strip() for p in cohort['papers'].values()}),
                  summary=_summary(rows), cases=rows, uncertainty_intervals=None,
                  limitations=['Synthetic controls do not estimate real-paper scientific-error accuracy.',
                    'External labels, reviewer independence, actual blinding and source authenticity are caller declarations, not authenticated.',
                    'Results concern predeclared structured discrepancies; prose mapping and overall scientific adequacy are unverified.',
                    'Case-level counts can be correlated within papers/groups; no sampling/cluster-adjusted uncertainty interval is estimated.',
                    'Pooled counts are descriptive; development/test strata must not be mistaken for independent held-out validation.'])
    for name, key in (('target', 'target_id'), ('discipline', 'discipline'), ('split', 'split')):
        report['by_'+name] = {value:_summary([row for row in rows if row[key] == value]) for value in sorted({row[key] for row in rows})}
    report['report_sha256'] = fingerprint(report)
    bounded_json(report, 4*1024*1024)
    return report


def error_benchmark_markdown(report):
    from sra.report import _safe_md
    lines = ['# Structured-check error benchmark', '',
             'Synthetic software controls only.' if report['dataset_kind'] == 'synthetic' else
             'Real-paper cohort with caller-declared labels; no independent scientific certification.', '',
             'Execution: '+report['execution_status'], 'Manifest SHA-256: '+report['manifest_sha256'],
             'Report SHA-256: '+report['report_sha256'], '']
    if report['schema_version'] == 'error-evaluation/1.0':
        sections = [('Pooled descriptive counts', report['summary'])]
        for category in ('split', 'target', 'discipline'):
            sections.extend((category+': '+key, value) for key, value in report['by_'+category].items())
        for title, summary in sections:
            lines.extend(['## '+_safe_md(title), '',
                          'Confusion: '+_safe_md(json_text(summary['confusion'])),
                          'Abstentions by gold label: '+_safe_md(json_text(summary['abstentions'])),
                          'Excluded labels: '+_safe_md(json_text(summary['excluded'])), '',
                          '| Metric | Numerator | Denominator | Value |', '| --- | --- | --- | --- |'])
            for name, metric in summary['metrics'].items():
                value = 'undefined' if metric['value'] is None else f"{metric['value']:.6g}"
                lines.append(f"| {_safe_md(name)} | {metric['numerator']} | {metric['denominator']} | {value} |")
            lines.append('')
    else:
        lines.extend(['| Case | Check status | Decision |', '| --- | --- | --- |'])
        for row in report['cases']:
            lines.append('| '+ ' | '.join(_safe_md(value) for value in (row['id'], row['check_result']['status'], row['prediction']))+' |')
    lines.extend(['', '## Limits', '', *('- '+_safe_md(value) for value in report['limitations'])])
    return '\n'.join(lines)+'\n'


def json_text(value):
    import json
    return json.dumps(value, sort_keys=True)
