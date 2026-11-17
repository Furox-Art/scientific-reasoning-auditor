"""Scoped record audits must not become whole-paper adequacy verdicts."""
import copy
from decimal import Overflow, Underflow, Inexact, ROUND_DOWN, localcontext
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.document import SourceIdentityError, load_document
from sra.review import review_manuscript
from sra.review_report import review_markdown
from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import digest, prepare_toolkit_spec

ROOT = Path(__file__).parents[1]


def checks():
    return json.loads((ROOT / 'examples/method-audits.json').read_text())['checks']


def spec(items):
    return dict(schema_version='1.0', checks=items)


class MethodAuditTests(unittest.TestCase):
    def run_check(self, item):
        return verify_toolkit_spec(spec([item]))['checks'][0]

    def test_known_results_are_repeatable_and_scoped(self):
        from sra.capabilities import capabilities
        from sra.toolkit_spec import KINDS
        self.assertEqual(set(capabilities()['deterministic_toolkit']['checks']), set(KINDS))
        self.assertEqual(len(KINDS), 35)
        original = spec(checks())
        before = copy.deepcopy(original)
        report = verify_toolkit_spec(original)
        self.assertEqual(report, verify_toolkit_spec(original))
        self.assertEqual(original, before)
        self.assertEqual([row['status'] for row in report['checks']], ['CANDIDATES', 'VERIFIED', 'VERIFIED', 'VERIFIED'])
        novelty, search, measurement, alignment = [row['details'] for row in report['checks']]
        self.assertEqual(novelty['scientific_novelty'], 'NOT_ASSESSED')
        self.assertEqual(novelty['comparisons'][0]['comparison'], 'different_declared_features')
        self.assertEqual(search['literature_adequacy'], 'NOT_ASSESSED')
        self.assertEqual(search['searches'][0]['age_days'], 1)
        self.assertTrue(search['deduplication']['arithmetic_agrees'])
        self.assertEqual(measurement['measurement_validity'], 'NOT_ASSESSED')
        self.assertEqual(alignment['method_appropriateness'], 'NOT_ASSESSED')
        self.assertEqual(measurement['mean_difference'], 0)
        self.assertAlmostEqual(measurement['sample_sd_difference'], math.sqrt(2.5))
        self.assertAlmostEqual(measurement['rmse'], math.sqrt(2))
        self.assertAlmostEqual(measurement['estimated_limits_of_agreement']['lower'], -1.96 * math.sqrt(2.5))

    def test_novelty_same_features_are_candidates_and_missing_mapping_abstains(self):
        item = checks()[0]
        comparator = item['comparators'][0]
        comparator.update(text='Sensor: optical.', sha256=digest('Sensor: optical.'))
        comparator['features']['sensor'] = dict(value='optical', quote='Sensor: optical.')
        row = self.run_check(item)
        self.assertEqual(row['status'], 'CANDIDATES')
        self.assertEqual(row['details']['same_feature_sources'], ['prior'])
        comparator['features']['sensor'] = None
        row = self.run_check(item)
        self.assertEqual(row['status'], 'UNDETERMINED')
        self.assertEqual(row['details']['unassessed_checks'], ['prior:sensor'])
        self.assertEqual(row['details']['comparisons'][0]['comparison'], 'unknown')

    def test_target_disagreements_are_literal_and_survive_other_unknowns(self):
        item = checks()[3]
        item['text'] += '\nAnalysis unit: hospital.'
        item['method']['analysis_unit'] = dict(value='hospital', quote='Analysis unit: hospital.')
        row = self.run_check(item)
        self.assertEqual(row['status'], 'REFUTED')
        self.assertEqual(row['details']['differences'], ['analysis_unit'])
        item['question']['contrast'] = None
        row = self.run_check(item)
        self.assertEqual(row['status'], 'UNDETERMINED')
        self.assertEqual(row['details']['differences'], ['analysis_unit'])
        self.assertEqual(row['details']['unassessed_checks'], ['contrast'])

    def test_search_audit_detects_age_chronology_counts_and_missing_records(self):
        item = checks()[1]
        item['required_sources'].append('index_b')
        item['searches'][0].update(query=None, searched_on='2026-01-01', coverage_start='2026-01-01', coverage_end='2020-01-01')
        item['deduplication']['records_after'] = 16
        row = self.run_check(item)
        self.assertEqual(row['status'], 'UNDETERMINED')
        self.assertEqual(row['details']['missing_sources'], ['index_b'])
        self.assertIn('search_1:older_than_caller_threshold', row['details']['issues'])
        self.assertIn('search_1:reversed_coverage_period', row['details']['issues'])
        self.assertIn('deduplication_count_mismatch', row['details']['issues'])
        item = checks()[1]
        item['searches'][0]['searched_on'] = '2026-11-18'
        self.assertEqual(self.run_check(item)['status'], 'REFUTED')
        item['searches'][0].update(searched_on=None, platform=None, records_found=None, coverage_start=None, coverage_end=None)
        item['deduplication']['records_before'] = None
        row = self.run_check(item)
        self.assertIsNone(row['details']['searches'][0]['age_days'])
        self.assertIsNone(row['details']['deduplication']['arithmetic_agrees'])
        self.assertEqual(row['status'], 'UNDETERMINED')
        item['searches'] = []
        self.assertEqual(self.run_check(item)['details']['missing_sources'], ['index_a'])

    def test_measurement_failure_abstention_boundaries_and_decimal_offsets(self):
        item = checks()[2]
        item['acceptable_difference'] = dict(lower=-2, upper=2)
        self.assertEqual(self.run_check(item)['status'], 'REFUTED')
        for key in ('independent_pairs', 'normal_differences', 'constant_bias_and_variance'):
            for value in (None, False):
                changed = dict(item, **{key: value})
                row = self.run_check(changed)
                self.assertEqual(row['status'], 'UNDETERMINED')
                self.assertIn(key, row['details']['unassessed_checks'])
        item['acceptable_difference'] = None
        self.assertIn('acceptable_difference', self.run_check(item)['details']['unassessed_checks'])
        item = checks()[2]
        item['measured'] = item['reference']
        self.assertIn('zero_observed_dispersion', self.run_check(item)['details']['unassessed_checks'])
        item = checks()[2]
        lower = self.run_check(item)['details']['estimated_limits_of_agreement']['lower']
        item['acceptable_difference']['lower'] = str(lower)
        self.assertIn('floating_point_boundary', self.run_check(item)['details']['unassessed_checks'])
        item = checks()[2]
        item.update(reference=['999999999999.99'] * 3, measured=['999999999999.991','999999999999.992','999999999999.993'])
        self.assertAlmostEqual(self.run_check(item)['details']['mean_difference'], .002)
        with localcontext() as context:
            context.prec = 3
            low_precision = self.run_check(item)
        self.assertEqual(low_precision, self.run_check(item))

    def test_ambient_decimal_exponents_traps_and_rounding_cannot_change_results_or_bounds(self):
        item = checks()[2]
        item['reference'] = [1e-30, 2e-30, 3e-30]
        item['measured'] = [1e-30, 3e-30, 5e-30]
        item['acceptable_difference'] = dict(lower=-1e-28, upper=1e-28)
        expected = self.run_check(item)
        for trap in (True, False):
            with localcontext() as context:
                context.prec = 2
                context.Emax = 5
                context.Emin = -5
                context.capitals = 0
                context.rounding = ROUND_DOWN
                context.traps[Overflow] = trap
                context.traps[Underflow] = trap
                context.traps[Inexact] = trap
                self.assertEqual(self.run_check(item), expected)
                invalid = checks()[2]
                invalid['acceptable_difference']['lower'] = '-1e13'
                with self.assertRaises(ValueError):
                    prepare_toolkit_spec(spec([invalid]))

    def test_source_binding_quotes_snapshots_and_read_only_behavior(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = Path(directory) / 'paper.md'
            original = (ROOT / 'examples/method-audits.md').read_bytes()
            paper.write_bytes(original)
            doc = load_document(paper)
            items = checks()
            for item in items:
                item.pop('text', None)
            bound = dict(spec(items), source_sha256=doc.sha256, extracted_text_sha256=digest(doc.text))
            report = review_manuscript(paper, study_type='quantitative', toolkit_spec=bound)
            self.assertEqual(paper.read_bytes(), original)
            self.assertTrue(all(row['scientific_verdict'] == 'NOT_ASSESSED' for row in report['criteria_matrix']['criteria']))
            rows = {row['id']: row for row in report['criteria_matrix']['criteria']}
            for criterion in ('novelty_and_literature','measurement_validity','systematic_search','design_and_confounding'):
                self.assertTrue(any(ref['module'] == 'toolkit' for ref in rows[criterion]['evidence']))
            for style in ('natural', 'technical'):
                text = review_markdown(report, style=style)
                self.assertIn('Bland-Altman', text)
                self.assertIn('NOT_ASSESSED', text)
            for index in (0,3):
                bad = copy.deepcopy(bound)
                bad['checks'][index]['text'] = doc.text
                with self.assertRaises(ValueError):
                    prepare_toolkit_spec(bad, doc)
            bad = copy.deepcopy(bound)
            bad['checks'][3]['method']['outcome']['quote'] = 'absent quotation'
            with self.assertRaises(SourceIdentityError):
                prepare_toolkit_spec(bad, doc)
            bad = copy.deepcopy(bound)
            bad['source_sha256'] = '0' * 64
            with self.assertRaises(SourceIdentityError):
                prepare_toolkit_spec(bad, doc)

    def test_malformed_inputs_rejected_before_loading_backends(self):
        originals = checks()
        bad = []
        for dimensions in ([], ['sensor','sensor'], ['bad name'], [3], 'sensor', ['d']*17):
            item = copy.deepcopy(originals[0]); item['dimensions'] = dimensions; bad.append(item)
        item = copy.deepcopy(originals[0]); item['comparators'][0]['sha256'] = '0'*64; bad.append(item)
        item = copy.deepcopy(originals[0]); item['comparators'] *= 2; bad.append(item)
        item = copy.deepcopy(originals[0]); item['comparators'][0]['features'] = {}; bad.append(item)
        item = copy.deepcopy(originals[0]); item['comparators'][0]['features']['sensor']['quote'] = 'absent'; bad.append(item)
        for sources in ([], ['a','a'], ['bad name'], [False], 'index'):
            item = copy.deepcopy(originals[1]); item['required_sources'] = sources; bad.append(item)
        for age in (-1, True, 36501, 2.5):
            item = copy.deepcopy(originals[1]); item['max_age_days'] = age; bad.append(item)
        for date in ('20261117', '2026-02-30', 20261117, '2026-11-17Z'):
            item = copy.deepcopy(originals[1]); item['as_of'] = date; bad.append(item)
        item = copy.deepcopy(originals[1]); item['searches'][0]['source'] = 'bad name'; bad.append(item)
        for count in (True,-1,100000001,1.5):
            item = copy.deepcopy(originals[1]); item['searches'][0]['records_found'] = count; bad.append(item)
        for values in ([1,2], '123', [1,2,'nan'], [1,2,True], [1,2,'1e13']):
            item = copy.deepcopy(originals[2]); item['reference'] = values; item['measured'] = values; bad.append(item)
        item = copy.deepcopy(originals[2]); item['measured'] = [1,2,3]; bad.append(item)
        item = copy.deepcopy(originals[2]); item['independent_pairs'] = 1; bad.append(item)
        for band in (dict(lower=2,upper=1),dict(lower=-1e13,upper=1),dict(lower=1,upper=1)):
            item = copy.deepcopy(originals[2]); item['acceptable_difference'] = band; bad.append(item)
        item = copy.deepcopy(originals[3]); item['method']['outcome']['value'] = 'absent value'; bad.append(item)
        item = copy.deepcopy(originals[3]); item['question'] = {}; bad.append(item)
        item = copy.deepcopy(originals[3]); item['method']['population'] = dict(value='',quote='Population: adults.'); bad.append(item)
        with patch('sra.toolkit._backend') as backend:
            for item in bad:
                with self.subTest(kind=item['kind']), self.assertRaises(ValueError):
                    prepare_toolkit_spec(spec([item]))
            backend.assert_not_called()
        item = copy.deepcopy(originals[0]); item['text'] = 'x'*100000
        item['contribution']['sensor'] = dict(value='x', quote='x')
        source = dict(id='other',text='y'*100000,sha256=digest('y'*100000),features=dict(sensor=dict(value='y',quote='y')))
        item['comparators'] = [dict(source),dict(source,id='other2')]
        with self.assertRaisesRegex(ValueError, '200000'):
            prepare_toolkit_spec(spec([item]))

    def test_cli_writes_separate_results(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'audit'
            result = subprocess.run([sys.executable,'-m','sra.cli','verify-toolkit',str(ROOT/'examples/method-audits.json'),'--out',str(out)], capture_output=True,text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(out.with_suffix('.json').read_text())
            self.assertEqual(len(report['checks']), 4)
            self.assertIn('NOT\\_ASSESSED',out.with_suffix('.md').read_text())
