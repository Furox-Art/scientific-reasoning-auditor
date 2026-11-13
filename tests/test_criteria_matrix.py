"""Coverage evidence is never a manuscript-level scientific verdict."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from sra.capabilities import capabilities
from sra.document import SourceIdentityError, load_document
from sra.review import review_manuscript
from sra.review_report import review_markdown


class CriteriaMatrixTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paper=Path(self.tmp.name)/'paper.md'
        self.paper.write_text('# Methods\nEthics approval number IRB-123 was reported.\n'
                              '# Results\nThe study found an association.\n'
                              '# Discussion\nThe scope remains uncertain.\n',encoding='utf-8')

    def review(self,**options):
        return review_manuscript(self.paper,**options)

    def rows(self,report):
        return {row['id']:row for row in report['criteria_matrix']['criteria']}

    def bound(self,checks):
        document=load_document(self.paper)
        return {'schema_version':'1.0','source_sha256':document.sha256,
                'extracted_text_sha256':hashlib.sha256(document.text.encode()).hexdigest(),
                'checks':checks}

    def test_offline_matrix_covers_important_domains_without_scientific_passes(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            report=self.review(study_type='quantitative')
        rows=self.rows(report)
        expected={'research_question','novelty_and_literature','design_and_confounding',
                  'sampling','measurement_validity','statistical_inference','multiplicity',
                  'missing_data','sample_size_power','robustness','ethics_and_consent',
                  'registration_and_protocol','conflicts_and_funding','citation_support',
                  'publication_updates','data_and_materials','code_reexecution',
                  'table_consistency','figure_interpretation','research_integrity',
                  'qualitative_credibility','reflexivity','systematic_search',
                  'proof_completeness','ml_validation','bayesian_diagnostics'}
        self.assertTrue(expected<=set(rows))
        self.assertGreaterEqual(len(rows),35)
        self.assertTrue(all(row['scientific_verdict']=='NOT_ASSESSED' for row in rows.values()))
        self.assertEqual(rows['novelty_and_literature']['execution_status'],'human_review_required')
        self.assertEqual(rows['code_reexecution']['execution_status'],'not_implemented')
        self.assertEqual(rows['research_integrity']['execution_status'],'not_implemented')
        self.assertNotIn('scientific_score',report['criteria_matrix'])
        self.assertEqual(report['execution_status'],'complete')

    def test_declared_types_conditional_and_unknown_applicability(self):
        for study_type in ('theoretical','qualitative','systematic-review','computational','unknown','mixed'):
            rows=self.rows(self.review(study_type=study_type))
            with self.subTest(study_type=study_type):
                if study_type in ('unknown','mixed'):
                    self.assertEqual(rows['sample_size_power']['applicability'],'requires_review')
                    self.assertEqual(rows['qualitative_credibility']['applicability'],'requires_review')
                elif study_type=='theoretical':
                    self.assertEqual(rows['sample_size_power']['applicability'],'not_applicable')
                    self.assertEqual(rows['proof_completeness']['applicability'],'applicable')
                elif study_type=='qualitative':
                    self.assertEqual(rows['qualitative_credibility']['applicability'],'applicable')
                    self.assertEqual(rows['sample_size_power']['applicability'],'not_applicable')
                elif study_type=='systematic-review':
                    self.assertEqual(rows['systematic_search']['applicability'],'applicable')
                else:
                    self.assertEqual(rows['ml_validation']['applicability'],'requires_review')
                self.assertEqual(rows['ethics_and_consent']['applicability'],'requires_review')

    def test_real_structured_results_retain_scope_and_conflicting_type(self):
        checks=[{'id':'p','kind':'power_analysis','design':'paired_t','mode':'calculate',
                 'nobs':34,'effect_size':'.5','alpha':'.05'},
                {'id':'ml','kind':'ml_validation','samples':[{'id':'a'},{'id':'b'}],
                 'splits':{'train':['a'],'test':['b']},'temporal':True},
                {'id':'adjust','kind':'statistical_analysis','operation':'multiple_testing',
                 'p_values':['.01','.04'],'method':'holm'}]
        report=self.review(study_type='theoretical',toolkit_spec=self.bound(checks))
        rows=self.rows(report)
        self.assertEqual(rows['sample_size_power']['applicability'],'requires_review')
        self.assertEqual(rows['sample_size_power']['execution_status'],'checks_completed')
        self.assertEqual(rows['ml_validation']['execution_status'],'partial')
        self.assertEqual(rows['multiplicity']['execution_status'],'checks_completed')
        self.assertEqual(rows['missing_data']['execution_status'],'not_applicable')
        self.assertEqual(rows['sample_size_power']['scientific_verdict'],'NOT_ASSESSED')
        refs=rows['sample_size_power']['evidence']
        self.assertEqual([r['check_id'] for r in refs if r['check_id']],['p'])
        for row in rows.values():
            for reference in row['evidence']:
                target=report
                for part in reference['pointer'].split('/')[1:]:
                    part=part.replace('~1','/').replace('~0','~')
                    target=target[int(part)] if isinstance(target,list) else target[part]
                self.assertIsInstance(target,dict)

    def test_profile_cues_never_certify_ethics(self):
        rows=self.rows(self.review(study_type='quantitative',disciplines=['clinical']))
        row=rows['ethics_and_consent']
        self.assertEqual(row['execution_status'],'screening_completed')
        self.assertTrue(row['human_review_required'])
        self.assertEqual(row['scientific_verdict'],'NOT_ASSESSED')
        self.assertTrue(any(r['check_id']=='ethics_identifier' for r in row['evidence']))

    def test_missing_backends_and_undetermined_checks_remain_visible(self):
        check={'id':'p','kind':'power_analysis','design':'paired_t','mode':'calculate',
               'nobs':34,'effect_size':'.5','alpha':'.05'}
        with patch('sra.toolkit._backend',side_effect=ImportError('backend')):
            report=self.review(study_type='quantitative',toolkit_spec=self.bound([check]))
        row=self.rows(report)['sample_size_power']
        self.assertEqual(row['execution_status'],'unavailable')
        self.assertEqual(row['evidence'][0]['check_status'],'UNAVAILABLE')
        with patch('statsmodels.stats.power.TTestPower.power',return_value=float('nan')):
            report=self.review(study_type='quantitative',toolkit_spec=self.bound([check]))
        self.assertEqual(self.rows(report)['sample_size_power']['execution_status'],'partial')

    def test_catalog_is_detached_hashed_and_matches_report(self):
        first=capabilities()['criteria_catalog']
        self.assertTrue(first['criteria'])
        old=first['catalog_sha256']
        first['criteria'][0]['required_evidence'].clear()
        second=capabilities()['criteria_catalog']
        self.assertTrue(second['criteria'][0]['required_evidence'])
        self.assertEqual(second['catalog_sha256'],old)
        self.assertEqual(self.review()['criteria_matrix']['catalog_sha256'],old)

    def test_catalog_selectors_refer_to_implemented_procedures_and_unique_criteria(self):
        from sra.domain_evidence import PROFILES
        from sra.toolkit_spec import KINDS
        catalog=capabilities()['criteria_catalog']['criteria']
        self.assertEqual(len({row['id'] for row in catalog}),len(catalog))
        profiles={rule.key for profile in PROFILES.values() for rule in profile['rules']}
        for row in catalog:
            self.assertTrue(set(row['profile_rules'])<=profiles)
            self.assertTrue({kind.split(':')[0] for kind in row['toolkit_checks']}<=set(KINDS))
            self.assertTrue(row['required_evidence'])

    def test_toolkit_failure_retains_requested_check_scope(self):
        check={'id':'p','kind':'power_analysis','design':'paired_t','mode':'calculate',
               'nobs':34,'effect_size':'.5','alpha':'.05'}
        with patch('sra.review.verify_prepared_toolkit',side_effect=RuntimeError('backend')):
            rows=self.rows(self.review(study_type='quantitative',toolkit_spec=self.bound([check])))
        self.assertEqual(rows['sample_size_power']['execution_status'],'failed')
        self.assertEqual(rows['sample_size_power']['evidence'][0]['pointer'],'/modules/toolkit')
        self.assertEqual(rows['multiplicity']['execution_status'],'not_requested')

    def test_screening_is_not_upgraded_by_available_structured_capability(self):
        rows=self.rows(self.review(study_type='quantitative',disciplines=['clinical']))
        self.assertEqual(rows['design_and_confounding']['execution_status'],'screening_completed')
        self.assertEqual(rows['sample_size_power']['execution_status'],'screening_completed')
        self.assertEqual(rows['statistical_inference']['execution_status'],'screening_completed')

    def test_general_screening_is_not_a_specialist_applicability_request(self):
        rows=self.rows(self.review(study_type='theoretical'))
        self.assertEqual(rows['design_and_confounding']['applicability'],'not_applicable')
        self.assertNotIn('conflict',rows['design_and_confounding']['applicability_reason'])

    def test_unverified_reported_statistics_remain_partial_even_with_other_disagreement(self):
        spec=json.loads((Path(__file__).parents[1]/'examples/extended_statistics.json').read_text())
        for value in (2.5,12345):
            with self.subTest(reported_t=value):
                spec['reported']={'t':value,'uncomputed':42}
                report=self.review(study_type='quantitative',statistics_spec=spec)
                original=report['modules']['statistics']['result']
                self.assertTrue(any(item['status']=='NOT_VERIFIED' for item in original['reported_checks']))
                self.assertEqual(self.rows(report)['statistical_inference']['execution_status'],'partial')
        spec.pop('reported')
        report=self.review(study_type='quantitative',statistics_spec=spec)
        self.assertEqual(self.rows(report)['statistical_inference']['execution_status'],'checks_completed')

    def test_svg_and_publication_snapshots_remain_screening_only(self):
        checks=[{'id':'svg','kind':'figure_svg','svg':'<svg><text>Axis</text></svg>'},
                {'id':'pub','kind':'publication_status','doi':'10.1000/paper','message':{'DOI':'10.1000/paper'}}]
        rows=self.rows(self.review(toolkit_spec=self.bound(checks)))
        for criterion in ('figure_interpretation','publication_updates'):
            self.assertEqual(rows[criterion]['execution_status'],'screening_completed')
            self.assertEqual(rows[criterion]['scientific_verdict'],'NOT_ASSESSED')

    def test_causal_adjustment_without_sensitivity_is_not_a_robustness_analysis(self):
        check={'id':'c','kind':'causal_graph','nodes':['T','Y'],'edges':[['T','Y']],
               'treatment':'T','outcome':'Y','observed':['T','Y'],'adjustment':[]}
        rows=self.rows(self.review(study_type='quantitative',toolkit_spec=self.bound([check])))
        self.assertEqual(rows['design_and_confounding']['execution_status'],'checks_completed')
        self.assertEqual(rows['robustness']['execution_status'],'not_requested')
        check['sensitivity_edges']=[]
        rows=self.rows(self.review(study_type='quantitative',toolkit_spec=self.bound([check])))
        self.assertEqual(rows['robustness']['execution_status'],'checks_completed')

    def test_failed_selected_profile_does_not_look_unrequested(self):
        with patch('sra.review.review_domain',side_effect=ImportError('profile')):
            rows=self.rows(self.review(study_type='quantitative',disciplines=['clinical']))
        self.assertEqual(rows['ethics_and_consent']['execution_status'],'unavailable')
        self.assertEqual(rows['ethics_and_consent']['evidence'][0]['module_status'],'unavailable')

    def test_scientific_ci_does_not_count_as_a_dimensional_check(self):
        root=Path(__file__).parents[1]
        spec=json.loads((root/'examples/advanced_scientific_checks.json').read_text())
        spec['checks']=[item for item in spec['checks'] if item['kind']=='semantic_ci']
        rows=self.rows(self.review(study_type='quantitative',scientific_spec=spec))
        self.assertEqual(rows['units_and_dimensions']['execution_status'],'not_requested')
        self.assertEqual(rows['units_and_dimensions']['evidence'],[])
        self.assertEqual(rows['statistical_inference']['execution_status'],'checks_completed')
        with patch('sra.review._prepare_spec',side_effect=ImportError('backend')):
            rows=self.rows(self.review(study_type='quantitative',scientific_spec=spec))
        self.assertEqual(rows['statistical_inference']['execution_status'],'unavailable')
        self.assertEqual(rows['units_and_dimensions']['execution_status'],'not_requested')

    def test_matrix_is_deterministic_source_bound_and_does_not_edit_inputs(self):
        original=self.paper.read_bytes()
        first=self.review(study_type='computational')['criteria_matrix']
        second=self.review(study_type='computational')['criteria_matrix']
        self.assertEqual(first,second)
        self.assertEqual(first['source_sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(self.paper.read_bytes(),original)
        from sra.criteria import build_criteria_matrix
        report=self.review()
        with self.assertRaises(ValueError):
            build_criteria_matrix('fiction',report['modules'],report['source_sha256'],report['extracted_text_sha256'])
        modules=copy.deepcopy(report['modules'])
        modules['writing']['source_sha256']='f'*64
        with self.assertRaises(SourceIdentityError):
            build_criteria_matrix('unknown',modules,report['source_sha256'],report['extracted_text_sha256'])

    def test_schema_and_markdown_expose_evidence_requirements_without_breaking_old_reports(self):
        root=Path(__file__).parents[1]
        schema=json.loads((root/'schemas/cross-disciplinary-review.schema.json').read_text())
        report=self.review(study_type='qualitative')
        self.assertIn('criteria_matrix',report)
        jsonschema.validate(report,schema)
        rendered=review_markdown(report)
        self.assertIn('Scientific criteria coverage',rendered)
        self.assertIn('Required evidence',rendered)
        self.assertIn('NOT_ASSESSED',rendered)
        broken=copy.deepcopy(report)
        broken['criteria_matrix']['criteria'][0]['scientific_verdict']='VERIFIED'
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(broken,schema)
        report.pop('criteria_matrix')
        jsonschema.validate(report,schema)
        self.assertIn('Coverage gaps',review_markdown(report))
