"""Descriptive pre-adjudication agreement on already validated reviewer records."""
from sra.error_benchmark import LABELS


def _fraction(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                value=numerator / denominator if denominator else None)


def reviewer_reliability(entries):
    """Four-category unweighted kappa; caller must validate complete records first.

    Columns are ordered by reviewer ID, not input order. A changing reviewer
    pair cannot be interpreted as a single pair's Cohen kappa. Unknown and
    inapplicable judgments remain categories, never negative labels.
    """
    pairs = {tuple(sorted(row['reviewer_id'] for row in entry['reviewers'])) for entry in entries}
    if len(pairs) != 1:
        return dict(status='not_assessed', reason='A fixed pair of declared reviewers is required.')
    first, second = next(iter(pairs))
    counts = {left: dict.fromkeys(LABELS, 0) for left in LABELS}
    for entry in entries:
        reviews = {row['reviewer_id']: row['label'] for row in entry['reviewers']}
        counts[reviews[first]][reviews[second]] += 1
    a = {label: sum(counts[label].values()) for label in LABELS}
    b = {label: sum(counts[left][label] for left in LABELS) for label in LABELS}
    n = len(entries)
    agreed = sum(counts[label][label] for label in LABELS)
    expected = sum(a[label] * b[label] for label in LABELS)
    return dict(status='descriptive', labels=list(LABELS), reviewer_a_id=first,
                reviewer_b_id=second, contingency=counts, reviewer_a_totals=a,
                reviewer_b_totals=b, raw_agreement=_fraction(agreed, n),
                expected_agreement=_fraction(expected, n*n),
                cohen_kappa=_fraction(n*agreed-expected, n*n-expected))


def agreement_markdown(agreement):
    from sra.report import _safe_md
    lines = ['## Pre-adjudication reviewer agreement', '',
             'Four nominal labels, including uncertain and not_applicable. Descriptive only;',
             'no independent expertise, blinding or cluster-adjusted uncertainty is established.', '']
    if agreement['status'] != 'descriptive':
        return lines + [_safe_md(agreement['reason']), '']
    lines += ['Rows: ' + _safe_md(agreement['reviewer_a_id']) +
              '; columns: ' + _safe_md(agreement['reviewer_b_id']) + '.', '',
              '| Label | ' + ' | '.join(agreement['labels']) + ' |',
              '| --- | ' + ' | '.join('---' for _ in agreement['labels']) + ' |']
    for label, values in agreement['contingency'].items():
        lines.append('| ' + label + ' | ' + ' | '.join(str(values[key]) for key in agreement['labels']) + ' |')
    lines += ['', '| Statistic | Numerator | Denominator | Value |', '| --- | --- | --- | --- |']
    for key, title in (('raw_agreement', 'Raw agreement'), ('expected_agreement', 'Expected agreement'),
                       ('cohen_kappa', 'Cohen kappa (unweighted)')):
        metric = agreement[key]
        value = 'undefined' if metric['value'] is None else f"{metric['value']:.6g}"
        lines.append(f"| {title} | {metric['numerator']} | {metric['denominator']} | {value} |")
    return lines + ['']
