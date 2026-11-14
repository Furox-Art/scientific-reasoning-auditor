"""Offline, prediction-free packaging for the frozen 2026-11-15 feasibility pilot.

Run from an installed source checkout. No network calls or numerical checks occur.
Human labels are accepted only by the separate merge subcommand.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

from sra.error_benchmark import bounded_json, error_label_template, prepare_manifest, records
from sra.error_evaluation import _gold
from sra.json_utils import canonical_json
from sra.toolkit_spec import _fields, digest

RECIPE = Path(__file__).resolve().parents[1] / 'benchmarks/pilots/20261115-selection.json'
TARGET = ('The printed statistic, printed degrees of freedom and reported p-value '
          'are incompatible under ordinary rounding to the displayed precision and '
          'two-sided t/z or upper-tail F/chi-square reference distributions. '
          'This conditional target does not establish test appropriateness, '
          'data authenticity or overall scientific validity.')
GUIDE = '''# Independent reviewer instructions

This is a small convenience feasibility exercise, not registered validation or
a representative sample. No reviewer identities, qualifications, independence
or decisions have been authenticated. Do not infer that a selected passage is
erroneous merely because it was selected.

Work independently. Read the complete original PDFs, methods and surrounding
results, not only the case quotes. The XML and normalized text are companion
snapshots; normalization flattens inline mathematical/table markup. The original
PDF is authoritative for visual notation. External supplements are not bundled;
if needed to decide a case, mark it uncertain and explain the missing evidence.
This package preparation inspected relevant contexts; it is not a complete
scientific peer review of the papers. Do not edit the articles.

In review-sheet.json, enter your own pseudonymous simple ASCII reviewer_id
(1-32 letters/digits/underscores; first character a letter).
For EVERY case set label to one of: error, no_error, uncertain, not_applicable.
Write a 20-2000 character rationale with your calculation, rounding, reference
distribution/sidedness, correction context and any mapping concerns. Preserve
all case IDs, manifest_sha256 and reviewer_slot. Do not insert a guessed decision
when context is insufficient. No identities or judgments have been prefilled.

error: discrepancy under the stated conditional target is supported.
no_error: compatibility under that target is supported; this is not study approval.
uncertain: evidence, rounding, mapping or assumptions cannot resolve the target.
not_applicable: this parametric target does not apply, for example a corrected,
permutation or exact-test p-value being compared with an ordinary reference tail.

Record discrepancies in source mapping explicitly. A printed t comparison uses
two-sided tails only as the target convention; the authors' actual sidedness is
not established by the package. Never treat a questionable mapping as a proven
scientific error. Do not see the other reviewer's decisions or automated results
before returning your own file. The organizer must obtain a third, distinct
adjudicator for any disagreement, including uncertain/not_applicable differences.
No performance estimates can be made from blank forms.
'''


def _json(value):
    # Canonical encoding preserves Decimal tokens accepted by the evaluator.
    return canonical_json(value) + '\n'


def review_sheet(cohort, slot):
    if slot not in ('A', 'B'):
        raise ValueError('Reviewer slot must be A or B.')
    return dict(schema_version='error-review-sheet/1.0',
                manifest_sha256=cohort['manifest_sha256'], reviewer_slot=slot,
                reviewer_id=None, cases=[dict(id=ident, label=None, rationale='')
                                         for ident in cohort['cases']])


def merge_reviews(manifest, reviewer_a, reviewer_b, adjudications=None):
    """Validate complete independent sheets; never create or infer human labels."""
    cohort = prepare_manifest(manifest)
    sheets = []
    for value, slot in ((reviewer_a, 'A'), (reviewer_b, 'B')):
        sheet = bounded_json(value)
        _fields(sheet, ('schema_version', 'manifest_sha256', 'reviewer_slot', 'reviewer_id', 'cases'))
        if (sheet['schema_version'] != 'error-review-sheet/1.0' or
                sheet['manifest_sha256'] != cohort['manifest_sha256'] or sheet['reviewer_slot'] != slot):
            raise ValueError('Reviewer sheet schema, frozen manifest or slot differs.')
        cases = records(sheet['cases'], 256)
        if set(cases) != set(cohort['cases']):
            raise ValueError('Every case, including negatives and unknowns, must be retained.')
        for row in cases.values():
            _fields(row, ('id', 'label', 'rationale'))
        sheets.append((sheet['reviewer_id'], cases))
    third = {}
    if adjudications is not None:
        value = bounded_json(adjudications)
        _fields(value, ('schema_version', 'manifest_sha256', 'cases'))
        if value['schema_version'] != 'error-adjudications/1.0' or value['manifest_sha256'] != cohort['manifest_sha256']:
            raise ValueError('Adjudication schema or frozen manifest differs.')
        third = {} if value['cases'] == [] else records(value['cases'], 256)
        if not set(third) <= set(cohort['cases']):
            raise ValueError('Adjudication refers to an unknown case.')
        for row in third.values():
            _fields(row, ('id', 'reviewer_id', 'label', 'rationale'))
    result = error_label_template(cohort['manifest'])
    for row in result['cases']:
        ident = row['id']
        row['reviewers'] = [dict(reviewer_id=reviewer_id, label=cases[ident]['label'],
                                 rationale=cases[ident]['rationale']) for reviewer_id, cases in sheets]
        if ident in third:
            row['adjudication'] = {k: v for k, v in third[ident].items() if k != 'id'}
    # Reuse evaluator requirements for distinct identities, complete rationales,
    # supported labels, and mandatory third-party resolution of disagreements.
    _gold(cohort, result)
    return result


def _zip(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2026, 11, 15, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, content.encode('utf-8') if isinstance(content, str) else content)
    return stream.getvalue()


def _inventory(files):
    return '\n'.join(f'{hashlib.sha256(value if isinstance(value, bytes) else value.encode("utf-8")).hexdigest()}  {key}'
                     for key, value in sorted(files.items())) + '\n'


def build_pack(sources, recipe=None):
    """Return deterministic ZIP bytes from exact, separately downloaded originals."""
    recipe = json.loads(RECIPE.read_text(encoding='utf-8')) if recipe is None else recipe
    assets, papers, cases, context = {}, [], [], ['# Source-bound cases\n', TARGET]
    for paper in recipe['included']:
        ident = paper['pmcid']
        for ext in ('xml', 'pdf'):
            expected = paper['files'][ext]
            path = Path(sources) / f'{ident}.{ext}'
            if path.stat().st_size != expected['bytes']:
                raise ValueError(f'Frozen source size differs: {ident}.{ext}')
            raw = path.read_bytes()
            if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
                raise ValueError(f'Frozen source bytes differ: {ident}.{ext}')
            assets[f'sources/{ident}.{ext}'] = raw
        raw = assets[f'sources/{ident}.xml']
        if b'<!ENTITY' in raw.upper():
            raise ValueError('XML entity declarations are not supported.')
        root = ET.fromstring(raw)
        # Include front, full body and back matter without character truncation.
        text = '\n\n'.join(' '.join(''.join(child.itertext()).split()) for child in root) + '\n'
        assets[f'sources/{ident}.txt'] = text
        papers.append(dict(id=ident, group_id=ident, split='development',
                           discipline=paper['discipline'], source_uri=paper['publisher_url'],
                           license_note=f"{paper['copyright']}; {paper['license']} {paper['license_url']}; "
                                        'normalized full JATS text; original PDF/XML supplied separately.',
                           text=text, sha256=digest(text)))
        context.append(f"\n## {paper['title']}\n\n{', '.join(paper['authors'])}. "
                       f"DOI: {paper['doi']}\n\n{paper['copyright']}; "
                       f"{paper['license']} {paper['license_url']}\n\nOriginal: {paper['publisher_url']}\n")
        paragraphs = root.findall('./body//p')
        for row in paper['cases']:
            passage = ' '.join(''.join(paragraphs[row['paragraph_index']].itertext()).split())
            if row['quote'] not in passage:
                raise ValueError('Frozen case quote is absent from the declared paragraph.')
            check = {k: row[k] for k in ('id', 'test', 'statistic', 'df', 'reported_p', 'relation')}
            check['kind'] = 'statistic_consistency'
            cases.append(dict(id=row['id'], paper_id=ident, target_id='reported_statistic',
                              source_quote=row['quote'], check=check))
            context.append(f"\n### {row['id']}\n\nOriginal PDF page {row['pdf_page']} "
                           f"(one-based).\n\nQuote: {row['quote']}\n\nFull paragraph: {passage}\n\n"
                           f"Mapping caveat: {row['mapping_note']}\n")
    manifest = dict(schema_version='error-benchmark/1.0',
                    dataset_id=recipe['pilot_id'], dataset_kind='real_papers',
                    papers=papers, targets=[dict(id='reported_statistic', kind='statistic_consistency',
                                                 definition=TARGET)], cases=cases)
    cohort = prepare_manifest(manifest)  # Preflight only; no backend execution.
    shared = dict(assets)
    shared.update({'INSTRUCTIONS.md': GUIDE, 'CASES.md': '\n'.join(context),
                   'source-index.json': _json(recipe)})
    outer = {'organizer/manifest.json': _json(manifest),
             'organizer/unfilled-labels.json': _json(error_label_template(manifest)),
             'organizer/selection.json': _json(recipe),
             'organizer/adjudications-template.json': _json(dict(schema_version='error-adjudications/1.0',
                 manifest_sha256=cohort['manifest_sha256'], cases=[]))}
    for slot in ('A', 'B'):
        files = dict(shared)
        # Reviewers receive quotes/caveats, never structured checks or predictions.
        files['source-index.json'] = _json({k: v for k, v in recipe.items() if k != 'included'} | {
            'included': [{k: v for k, v in p.items() if k != 'cases'} for p in recipe['included']]})
        files['review-sheet.json'] = json.dumps(review_sheet(cohort, slot), ensure_ascii=False, indent=2) + '\n'
        files['SHA256SUMS'] = _inventory(files)
        outer[f'reviewer-{slot}.zip'] = _zip(files)
    outer['README.md'] = (RECIPE.parent / '20261115-README.md').read_text(encoding='utf-8')
    outer['SHA256SUMS'] = _inventory(outer)
    return _zip(outer)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--sources', required=True, type=Path)
    build.add_argument('--out', required=True, type=Path)
    merge = commands.add_parser('merge')
    for name in ('manifest', 'reviewer-a', 'reviewer-b'):
        merge.add_argument('--' + name, required=True, type=Path)
    merge.add_argument('--adjudications', type=Path)
    merge.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == 'build':
        payload = build_pack(args.sources)
    else:
        read = lambda path: path.read_text(encoding='utf-8')
        payload = _json(merge_reviews(read(args.manifest), read(args.reviewer_a), read(args.reviewer_b),
                                      read(args.adjudications) if args.adjudications else None)).encode('utf-8')
    # Exclusive creation rejects preexisting files, hardlinks and symlink targets.
    with args.out.open('xb') as stream:
        stream.write(payload)
    print(f'Wrote {args.out} ({len(payload)} bytes); no human decisions generated.')


if __name__ == '__main__':
    main()
