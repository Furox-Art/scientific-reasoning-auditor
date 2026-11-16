"""Offline post-hoc source extraction/replay controls, never paper-error accuracy."""
import argparse
from collections import Counter
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

import sra
from sra.document import parse_document_text
from sra.inspection import prepare_inspection
from sra.toolkit import verify_toolkit_spec, _numerical_environment

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'benchmarks/pilots/statistic-preparation-20261116'
COHORT = ROOT / 'benchmarks/pilots/multifield-20261116'
PINS = {
    'cases.json': '31c8be3c31bbc440f76e17e6348b3789c1ae74865ea3b2e7fd10f707ead8cde9',
    'protocol.md': 'b22bbce0ef13ede8500438becd25746b34e0dc69b0a9b8f17430e73777c71efc',
}
INVENTORY_SHA = '7ae14fad08d2945ac450543af74cfaf7f6b75bab99d8d6498d662bbd5db60551'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected):
    with path.open('rb') as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000 or sha(raw) != expected:
        raise ValueError('Frozen development/source bytes changed; create a new version.')
    return raw


def evaluate():
    packet = json.loads(pinned(FOLDER / 'cases.json', PINS['cases.json']))
    pinned(FOLDER / 'protocol.md', PINS['protocol.md'])
    inventory = json.loads(pinned(COHORT / 'sources.json', INVENTORY_SHA))
    source = FOLDER / packet['source']
    raw = pinned(source, packet['source_sha256'])
    document = parse_document_text(raw.decode('utf-8'), source=str(source),
        sha256=sha(raw), input_format='md')
    prepared = prepare_inspection(document)
    cases = []
    for case in packet['cases']:
        if document.text[case['start']:case['end']] != case['source_quote']:
            raise ValueError('Source case quotation/offset mismatch.')
        matches = [row for row in prepared['candidates'] if
                   (row['start'], row['end'], row['source_quote']) ==
                   (case['start'], case['end'], case['source_quote'])]
        draft = matches[0].get('suggested_check') if len(matches) == 1 else None
        recovered = draft is not None and all(draft.get(k) == v for k, v in case['expected'].items())
        row = dict(id=case['id'], source_quote=case['source_quote'], start=case['start'], end=case['end'],
                   literal_recovered=recovered, draft=draft, semantic_mapping_confirmed=False,
                   paper_error_label=None, unconfirmed_result=None, conditional_result=None)
        if recovered:
            if (draft['alternative'] != 'unknown' or draft['df_precision'] != 'unknown'
                    or matches[0]['requires_confirmation'] is not True):
                raise ValueError('Preparation silently resolved a scientific assumption.')
            def execute(check):
                return verify_toolkit_spec(dict(schema_version='1.0',
                    source_sha256=document.sha256, extracted_text_sha256=sha(document.text.encode()),
                    checks=[check]), document)['checks'][0]
            row['unconfirmed_result'] = execute(draft)
            # Deliberately supplied scenario, NOT an inferred/confirmed paper mapping.
            conditional = dict(draft, alternative='greater', df_precision='exact')
            result = execute(conditional)
            with localcontext() as context:
                context.prec = 60
                value = Decimal(draft['statistic'])
                half = Decimal(1).scaleb(value.as_tuple().exponent) / 2
                lower = (-(value + half) / 2).exp()
                upper = (-(value - half) / 2).exp()
            actual = result['details'].get('computed_p_interval')
            reference_matches = (isinstance(actual, list) and len(actual) == 2 and
                all(abs(Decimal.from_float(a) - b) < Decimal('1e-14')
                    for a, b in zip(actual, (lower, upper))))
            row.update(conditional_result=result,
                conditional_reference='Central chi-square upper tail, exact df=2, printed decimal rounding.',
                reference_appropriateness_for_paper='NOT_ESTABLISHED',
                analytic_df2_reference_interval=[str(lower), str(upper)],
                analytic_reference_matches_within_1e_14=reference_matches)
        cases.append(row)
    papers = []
    for entry in inventory['papers']:
        row = dict(doi=entry['doi'], stratum=entry['stratum'], source_status=entry['status'])
        if entry['status'] == 'available':
            path = COHORT / entry['text']
            raw = pinned(path, entry['text_sha256'])
            document = parse_document_text(raw.decode('utf-8'), source=str(path),
                sha256=sha(raw), input_format='md')
            result = prepare_inspection(document)
            row.update(source_sha256=entry['text_sha256'], checks_executed=result['checks_executed'],
                candidates_by_kind=dict(Counter(c['kind'] for c in result['candidates'])),
                suggested_checks=sum(c.get('suggested_check') is not None for c in result['candidates']))
        papers.append(row)
    package = Path(sra.__file__).resolve().parent
    runtime = {p.relative_to(package).as_posix(): sha(p.read_bytes()) for p in sorted(package.rglob('*'))
               if p.is_file() and (p.suffix == '.py' or p.name == 'py.typed')}
    return dict(schema_version='source-statistic-development/1.0', engine_version=sra.__version__,
        scope='Post-hoc extraction and conditional arithmetic development controls; no scientific accuracy estimate.',
        source_doi=packet['doi'], source_sha256=packet['source_sha256'], frozen_inputs_sha256=PINS,
        inventory_sha256=INVENTORY_SHA, producer_sha256=sha(Path(__file__).read_bytes()),
        numerical_environment=_numerical_environment(), runtime_source_files=runtime,
        cases=cases, literal_cases=len(cases), literal_recovered=sum(r['literal_recovered'] for r in cases),
        unconfirmed_status_counts=dict(Counter(r['unconfirmed_result']['status'] for r in cases if r['unconfirmed_result'])),
        conditional_status_counts=dict(Counter(r['conditional_result']['status'] for r in cases if r['conditional_result'])),
        new_human_labels=0, scientific_error_accuracy=None, paper_sweep=papers,
        limits=['Three triplets from one development paper are not three independent papers.',
                'Kruskal-Wallis and Bonferroni-adjusted Dunn comparisons are stated in the methods.',
                'Central-reference, tail, exact df and printed rounding scenario is supplied, not authenticated.',
                'A conditional REFUTED result is not a confirmed paper error or misconduct finding.',
                'No raw data, original figure images, supplements or analysis code were reproduced.',
                'The original twelve-paper first result remains unchanged; this is development reuse.',
                'Analytic numerical agreement is a software control, not a formal backend error bound.'])


def markdown(report):
    lines = ['# Literal source-statistic development controls', '', report['scope'], '',
        f"Literal recovery: {report['literal_recovered']} / {report['literal_cases']} frozen development triplets.",
        'Unconfirmed statuses: ' + json.dumps(report['unconfirmed_status_counts'], sort_keys=True),
        'Conditional statuses: ' + json.dumps(report['conditional_status_counts'], sort_keys=True),
        'Scientific-error accuracy: not estimated. New human labels: 0.', '',
        '| Source triplet | Unconfirmed | Conditional scenario | Analytic reference agreement |',
        '| --- | --- | --- | --- |']
    for row in report['cases']:
        lines.append('| ' + ' | '.join((row['source_quote'],
            (row['unconfirmed_result'] or {}).get('status', 'NOT_RECOVERED'),
            (row['conditional_result'] or {}).get('status', 'NOT_RUN'),
            str(row.get('analytic_reference_matches_within_1e_14')))) + ' |')
    lines += ['', '## Complete frozen-source sweep', '',
              '| DOI | Subject-tag stratum | Source | Proposed checks |', '| --- | --- | --- | ---: |']
    for row in report['paper_sweep']:
        lines.append(f"| {row['doi']} | {row['stratum']} | {row['source_status']} | {row.get('suggested_checks', 'not_run')} |")
    lines += ['', '## Limits', '', *('- ' + value for value in report['limits']), '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    targets = [args.out.with_suffix(suffix) for suffix in ('.json', '.md')]
    if any(p.exists() or p.is_symlink() for p in targets):
        raise FileExistsError('Choose a fresh output prefix; existing results are preserved.')
    report = evaluate()
    for path, value in zip(targets, (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', markdown(report))):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(value)
    print(json.dumps({k: report[k] for k in ('literal_cases', 'literal_recovered', 'unconfirmed_status_counts', 'conditional_status_counts')}))
    if not (report['literal_recovered'] == report['literal_cases'] == 3
            and report['unconfirmed_status_counts'] == {'UNDETERMINED': 3}
            and all(r.get('analytic_reference_matches_within_1e_14') for r in report['cases'])):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
