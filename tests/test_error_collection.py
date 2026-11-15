"""Synthetic collection controls; never actual human labels or performance evidence."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from sra.error_benchmark import prepare_manifest, run_error_benchmark, fingerprint
from sra.error_evaluation import evaluate_errors, error_benchmark_markdown
from tools import error_review_pack as collection
from test_error_benchmark import fixture, labels


def sheets(manifest):
    cohort = prepare_manifest(manifest)
    result = [collection.review_sheet(cohort, slot) for slot in ('A', 'B')]
    decisions = [('error', 'error', 'no_error', 'no_error', 'uncertain', 'uncertain', 'not_applicable', 'not_applicable'),
                 ('error', 'no_error', 'no_error', 'uncertain', 'uncertain', 'not_applicable', 'not_applicable', 'error')]
    for sheet, values in zip(result, decisions):
        sheet['reviewer_id'] = 'synthetic_' + sheet['reviewer_slot']
        for row, label in zip(sheet['cases'], values):
            row.update(label=label, rationale='Synthetic collection control; no actual reviewer decision.')
    return result


class ErrorCollectionTests(unittest.TestCase):
    def test_inspection_reports_four_class_agreement_without_resolving_disputes(self):
        manifest = fixture(); a, b = sheets(manifest)
        before = copy.deepcopy((manifest, a, b))
        with patch('sra.toolkit._backend', side_effect=AssertionError('No checks during collection')):
            report = collection.inspect_reviews(manifest, a, b)
        agreement = report['reviewer_reliability']
        self.assertEqual(agreement['status'], 'descriptive')
        self.assertEqual(agreement['raw_agreement'], dict(numerator=4, denominator=8, value=.5))
        self.assertEqual(agreement['expected_agreement']['value'], .25)
        self.assertAlmostEqual(agreement['cohen_kappa']['value'], 1/3)
        self.assertEqual(agreement['contingency']['error']['no_error'], 1)
        self.assertEqual(agreement['reviewer_a_totals'], dict.fromkeys(agreement['labels'], 2))
        self.assertEqual(report['unresolved_case_ids'], ['m1', 'm3', 'c1', 'c3'])
        self.assertEqual(report['adjudications_template']['cases'][0],
                         dict(id='m1', reviewer_id=None, label=None, rationale=''))
        self.assertFalse(report['reviewer_identity_verified'])
        self.assertEqual(report['schema_version'], 'error-review-inspection/1.0')
        self.assertNotIn('prediction', report)
        self.assertEqual(report['report_sha256'], fingerprint({k:v for k,v in report.items() if k != 'report_sha256'}))
        self.assertEqual(before, (manifest, a, b))
        with self.assertRaises(ValueError):collection.merge_reviews(manifest, a, b)

    def test_undefined_kappa_and_complete_sheet_validation(self):
        manifest = fixture(); a, b = sheets(manifest)
        for sheet in (a, b):
            for row in sheet['cases']:row['label'] = 'uncertain'
        report = collection.inspect_reviews(manifest, a, b)
        self.assertEqual(report['unresolved_case_ids'], [])
        self.assertEqual(report['reviewer_reliability']['raw_agreement']['value'], 1)
        self.assertIsNone(report['reviewer_reliability']['cohen_kappa']['value'])
        self.assertEqual(report['reviewer_reliability']['cohen_kappa']['denominator'], 0)
        mutations = []
        for key, value in [('reviewer_id', b['reviewer_id']), ('manifest_sha256', '0'*64),
                           ('reviewer_slot', 'B'), ('schema_version', 'wrong'), ('cases', []), ('extra', True)]:
            bad = copy.deepcopy(a); bad[key] = value; mutations.append(bad)
        for key, value in [('label', None), ('rationale', ''), ('label', []), ('extra', 'x')]:
            bad = copy.deepcopy(a); bad['cases'][0][key] = value; mutations.append(bad)
        bad = copy.deepcopy(a); bad['cases'].pop(); mutations.append(bad)
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(ValueError):collection.inspect_reviews(manifest, bad, b)

    def test_generic_packet_contains_full_snapshots_but_no_executable_mapping(self):
        manifest = fixture()
        manifest['papers'][0]['text'] += '\nFull snapshot end sentinel.\n'
        manifest['papers'][0]['sha256'] = hashlib.sha256(manifest['papers'][0]['text'].encode()).hexdigest()
        before = copy.deepcopy(manifest)
        with patch('sra.toolkit._backend', side_effect=AssertionError('No checks during packaging')):
            payload = collection.build_cohort_pack(manifest)
            self.assertEqual(payload, collection.build_cohort_pack(manifest))
        with zipfile.ZipFile(io.BytesIO(payload)) as outer:
            self.assertEqual(json.loads(outer.read('organizer/manifest.json')), manifest)
            for slot in ('A', 'B'):
                with zipfile.ZipFile(io.BytesIO(outer.read(f'reviewer-{slot}.zip'))) as inner:
                    self.assertEqual(inner.read('sources/p0.txt').decode(), manifest['papers'][0]['text'])
                    context = json.loads(inner.read('cases.json'))
                    self.assertEqual(len(context['cases']), 8)
                    self.assertNotIn('check', context['cases'][0])
                    self.assertEqual(context['cases'][0]['source_quote'], manifest['cases'][0]['source_quote'])
                    index = json.loads(inner.read('source-index.json'))
                    self.assertNotIn('group_id', index['papers'][0])
                    self.assertNotIn('split', index['papers'][0])
                    self.assertNotIn('kind', context['targets'][0])
                    self.assertIsNone(json.loads(inner.read('review-sheet.json'))['cases'][0]['label'])
                    for line in inner.read('SHA256SUMS').decode().splitlines():
                        sha, name = line.split('  ', 1)
                        self.assertEqual(sha, hashlib.sha256(inner.read(name)).hexdigest())
        self.assertEqual(before, manifest)

    def test_inspection_packet_hides_reviewer_decisions_from_adjudicator(self):
        manifest = fixture(); a, b = sheets(manifest)
        payload = collection.build_inspection_pack(manifest, a, b)
        with zipfile.ZipFile(io.BytesIO(payload)) as outer:
            report = json.loads(outer.read('organizer/review-inspection.json'))
            self.assertIn('Cohen', outer.read('organizer/review-inspection.md').decode())
            self.assertEqual(len(report['unresolved_case_ids']), 4)
            with zipfile.ZipFile(io.BytesIO(outer.read('adjudicator.zip'))) as inner:
                template = json.loads(inner.read('adjudications.json'))
                self.assertEqual([row['id'] for row in template['cases']], report['unresolved_case_ids'])
                self.assertTrue(all(row['label'] is None and row['reviewer_id'] is None for row in template['cases']))
                context = json.loads(inner.read('cases.json'))
                self.assertEqual(len(context['cases']), 4)
                for name in inner.namelist():
                    raw = inner.read(name).decode()
                    self.assertNotIn('synthetic_A', raw)
                    self.assertNotIn('synthetic_B', raw)
                    self.assertNotIn('Synthetic collection control', raw)
        for sheet in (a, b):
            for row in sheet['cases']:row['label'] = 'uncertain'
        with zipfile.ZipFile(io.BytesIO(collection.build_inspection_pack(manifest, a, b))) as outer:
            self.assertNotIn('adjudicator.zip', outer.namelist())

    def test_collection_cli_is_exclusive_and_reads_bounded_inputs(self):
        manifest = fixture(); a, b = sheets(manifest)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, value in [('manifest', manifest), ('a', a), ('b', b)]:
                (root/f'{name}.json').write_text(json.dumps(value), encoding='utf-8')
            for command in ('build-cohort', 'inspect'):
                argv = [command, '--manifest', str(root/'manifest.json'), '--out', str(root/f'{command}.zip')]
                if command == 'inspect':argv += ['--reviewer-a', str(root/'a.json'), '--reviewer-b', str(root/'b.json')]
                collection.main(argv)
                with self.assertRaises(FileExistsError):collection.main(argv)
                self.assertTrue(zipfile.is_zipfile(root/f'{command}.zip'))
            (root/'a.json').write_text(' '* (1024*1024+1), encoding='utf-8')
            with self.assertRaises(ValueError):collection.main(['inspect', '--manifest', str(root/'manifest.json'),
                '--reviewer-a', str(root/'a.json'), '--reviewer-b', str(root/'b.json'), '--out', str(root/'bad.zip')])
            self.assertFalse((root/'bad.zip').exists())

    def test_evaluation_retains_grouped_denominators_and_preadjudication_agreement(self):
        manifest = fixture(); run = run_error_benchmark(manifest); gold = labels(manifest)
        report = evaluate_errors(manifest, run, gold)
        self.assertIn('by_group', report)
        self.assertEqual(report['by_group']['g0']['total_cases'], 2)
        self.assertEqual(report['by_paper']['p1']['total_cases'], 6)
        self.assertEqual(report['cases'][0]['group_id'], 'g0')
        self.assertEqual(report['reviewer_reliability']['raw_agreement']['value'], 1)
        sensitivity = report['group_sensitivity']
        self.assertEqual(sensitivity['status'], 'descriptive')
        self.assertEqual(sensitivity['omissions'][0]['omitted_group_id'], 'g0')
        self.assertEqual(sensitivity['omissions'][0]['remaining_group_count'], 1)
        self.assertEqual(sensitivity['omissions'][0]['summary'], report['by_group']['g1'])
        markdown = error_benchmark_markdown(report)
        self.assertIn('Pre-adjudication reviewer agreement', markdown)
        self.assertIn('Leave-one-group-out', markdown)
        # Changing order must not silently change the meaning of reviewer columns.
        for case in gold['cases'][::2]:case['reviewers'].reverse()
        reverse = evaluate_errors(manifest, run, gold)
        self.assertEqual(reverse['reviewer_reliability'], report['reviewer_reliability'])
        gold['cases'][0]['reviewers'][0]['reviewer_id'] = 'other_synthetic_reviewer'
        mixed = evaluate_errors(manifest, run, gold)
        self.assertEqual(mixed['reviewer_reliability']['status'], 'not_assessed')
        self.assertNotIn('cohen_kappa', mixed['reviewer_reliability'])
        self.assertIn('fixed pair', error_benchmark_markdown(mixed))

    def test_kappa_retains_negative_agreement_and_precedes_adjudication(self):
        from sra.error_reliability import reviewer_reliability
        pairs = [('error', 'no_error'), ('no_error', 'error')]
        entries = [dict(reviewers=[dict(reviewer_id=who, label=value) for who, value in
                                  zip(('synthetic_A', 'synthetic_B'), pair)]) for pair in pairs]
        metric = reviewer_reliability(entries)['cohen_kappa']
        self.assertEqual(metric, dict(numerator=-2, denominator=2, value=-1))
        manifest = fixture(); a, b = sheets(manifest)
        inspected = collection.inspect_reviews(manifest, a, b)
        third = copy.deepcopy(inspected['adjudications_template'])
        for row in third['cases']:
            row.update(reviewer_id='synthetic_third', label='uncertain',
                       rationale='Synthetic adjudication control; no actual expert was involved.')
        gold = collection.merge_reviews(manifest, a, b, third)
        evaluated = evaluate_errors(manifest, run_error_benchmark(manifest), gold)
        self.assertEqual(evaluated['reviewer_reliability'], inspected['reviewer_reliability'])
        self.assertEqual(evaluated['reviewer_agreement']['value'], .5)

    def test_group_sensitivity_requires_two_independent_declared_groups(self):
        manifest = fixture()
        for paper in manifest['papers']:paper.update(group_id=' g0 ', split='development')
        report = evaluate_errors(manifest, run_error_benchmark(manifest), labels(manifest))
        self.assertEqual(report['group_count'], 1)
        self.assertEqual(report['group_sensitivity']['status'], 'not_assessed')
        self.assertEqual(report['group_sensitivity']['omissions'], [])
        self.assertEqual(list(report['by_group']), ['g0'])


if __name__ == '__main__':
    unittest.main()
