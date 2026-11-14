"""Synthetic evaluator controls; no real experts or scientific accuracy labels."""
import copy
import json
import contextlib
import io
import os
from types import SimpleNamespace
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from decimal import Decimal
from sra.json_utils import canonical_json

from sra.error_benchmark import (fingerprint, prepare_manifest, run_error_benchmark,
                                 error_label_template)
from sra.error_evaluation import evaluate_errors, error_benchmark_markdown
from sra.toolkit_spec import digest
from sra.cli import main
from sra.error_benchmark import bounded_json
from sra.error_benchmark_cli import _read, execute_error_command


def fixture():
    papers = []
    for i, split in enumerate(('development', 'test')):
        text = f'# Synthetic paper {i}\nEquations require explicit checking.\n'
        text += '\n'.join(f'Source passage number {n} contains five common words.' for n in range(4))
        papers.append(dict(id=f'p{i}', group_id=f'g{i}', split=split,
                           discipline=('physics', 'computing')[i], source_uri=f'synthetic:p{i}',
                           license_note='Synthetic test fixture, project MIT license.', text=text, sha256=digest(text)))
    targets = [dict(id='algebra', kind='polynomial_identity', definition='Declared polynomial sides disagree.'),
               dict(id='context', kind='source_overlap', definition='Semantic adequacy requires separate human review.')]
    cases = []
    for n, right in enumerate(('2*x', '3*x', '4*x', '2*x')):
        cases.append(dict(id=f'm{n}', paper_id=f'p{n//2}', target_id='algebra',
                          source_quote='Equations require explicit checking.',
                          check=dict(id=f'm{n}', kind='polynomial_identity', variables=['x'], left='x+x', right=right)))
    text = 'five common words used in scientific writing'
    for n in range(4):
        cases.append(dict(id=f'c{n}', paper_id='p1', target_id='context',
                          source_quote=f'Source passage number {n} contains five common words.',
                          check=dict(id=f'c{n}', kind='source_overlap', min_tokens=5,
                                     sources=[dict(id='source', text=text, sha256=digest(text))])))
    return dict(schema_version='error-benchmark/1.0', dataset_id='synthetic_controls',
                dataset_kind='synthetic', papers=papers, targets=targets, cases=cases)


def labels(manifest):
    result = error_label_template(manifest)
    outcomes = ('no_error', 'error', 'no_error', 'error', 'error', 'no_error', 'uncertain', 'not_applicable')
    for case, label in zip(result['cases'], outcomes):
        case['reviewers'] = [dict(reviewer_id=f'fixture_{r}', label=label,
                                  rationale='Synthetic software test decision; no actual reviewer.') for r in ('a', 'b')]
    return result


def numeric_boundary():
    manifest=fixture()
    manifest['papers']=manifest['papers'][:1]
    text='A length of 9007199254740993.0 m was reported as 9007199254740992.0 m.'
    manifest['papers'][0].update(text=text,sha256=digest(text))
    manifest['targets']=[dict(id='algebra',kind='unit_conversion',definition='The declared meter value differs from the reported value.')]
    case=manifest['cases'][0]
    case['source_quote']=text
    case['check']=dict(id=case['id'],kind='unit_conversion',value='9007199254740993.0',reported='9007199254740992.0',from_unit='m',to_unit='m',atol='0')
    manifest['cases']=[case]
    return json.dumps(manifest).replace('"9007199254740993.0"','9007199254740993.0').replace('"9007199254740992.0"','9007199254740992.0')


class ErrorBenchmarkTests(unittest.TestCase):
    def test_raw_json_decimal_tokens_survive_runner_and_cli_ingestion(self):
        raw=numeric_boundary()
        run=run_error_benchmark(raw)
        self.assertEqual(run['cases'][0]['check_result']['status'],'REFUTED')
        self.assertEqual(run['cases'][0]['prediction'],'error')
        manifest=json.loads(raw,parse_float=Decimal)
        self.assertEqual(run,run_error_benchmark(manifest))
        self.assertNotEqual(fingerprint(manifest),fingerprint(json.loads(raw)))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'manifest.json';path.write_text(raw)
            with patch('sys.argv',['sra','benchmark-errors',str(path),'--out',str(Path(directory)/'run')]),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(),0)
            result=json.loads((Path(directory)/'run.json').read_text())
            self.assertEqual(result['cases'][0]['prediction'],'error')

    def test_declared_publication_identity_cannot_cross_splits_or_groups(self):
        manifest=fixture()
        manifest['papers'][0]['source_uri']='https://example.org/paper'
        manifest['papers'][1]['source_uri']='  https://example.org/paper  '
        with self.assertRaises(ValueError):prepare_manifest(manifest)
        manifest['papers'][1]['split']='development'
        with self.assertRaises(ValueError):prepare_manifest(manifest)
        manifest['papers'][1]['group_id']='g0'
        self.assertEqual(len(prepare_manifest(manifest)['papers']),2)
    def test_actual_backend_execution_repeatability_and_scoped_abstention(self):
        manifest = fixture()
        first = run_error_benchmark(manifest)
        self.assertEqual(first, run_error_benchmark(json.dumps(manifest)))
        by_id = {case['id']: case for case in first['cases']}
        self.assertEqual(by_id['m0']['prediction'], 'no_error')
        self.assertEqual(by_id['m1']['prediction'], 'error')
        self.assertEqual(by_id['c0']['prediction'], 'abstain')
        self.assertEqual(by_id['c0']['check_result']['status'], 'CANDIDATES')
        self.assertEqual(first['manifest_sha256'], fingerprint(manifest))
        self.assertEqual(first['mapping_semantics_verified'], False)
        self.assertEqual(first['dataset_kind'], 'synthetic')
        self.assertEqual(manifest, fixture())

    def test_exact_denominators_include_abstained_errors(self):
        manifest = fixture()
        report = evaluate_errors(manifest, run_error_benchmark(manifest), labels(manifest))
        total = report['summary']
        self.assertEqual(total['confusion'], dict(tp=1, fp=1, fn=1, tn=1))
        self.assertEqual(total['excluded'], dict(uncertain=1, not_applicable=1))
        self.assertEqual(total['abstentions'], dict(error=1, no_error=1))
        self.assertEqual(total['metrics']['decision_coverage'], dict(numerator=4, denominator=6, value=4/6))
        self.assertEqual(total['metrics']['end_to_end_recall']['value'], 1/3)
        self.assertEqual(total['metrics']['decided_recall']['value'], .5)
        self.assertEqual(total['metrics']['selective_risk']['value'], .5)
        self.assertEqual(set(report['by_split']), {'development', 'test'})
        self.assertEqual(report['by_target']['context']['metrics']['decided_precision']['value'], None)
        self.assertEqual(report['uncertainty_intervals'], None)
        self.assertIn('Synthetic', error_benchmark_markdown(report))

    def test_unknown_and_excluded_labels_do_not_become_negatives(self):
        manifest = fixture()
        gold = labels(manifest)
        for case in gold['cases']:
            for reviewer in case['reviewers']:
                reviewer['label'] = 'uncertain'
        result = evaluate_errors(manifest, run_error_benchmark(manifest), gold)
        self.assertTrue(all(metric['value'] is None for metric in result['summary']['metrics'].values()))
        self.assertEqual(sum(result['summary']['confusion'].values()), 0)

    def test_missing_backend_and_calculations_abstain(self):
        manifest = fixture()
        with patch('sra.toolkit._backend', side_effect=ImportError('not installed')):
            report = run_error_benchmark(manifest)
        self.assertTrue(all(case['prediction'] == 'abstain' for case in report['cases']))
        self.assertEqual(report['execution_status'], 'partial')
        result = evaluate_errors(manifest, report, labels(manifest))
        self.assertEqual(result['summary']['metrics']['decision_coverage']['value'], 0)
        self.assertEqual(result['summary']['metrics']['end_to_end_recall']['value'], 0)
        manifest = fixture()
        manifest['papers'] = manifest['papers'][:1]
        manifest['targets'] = [dict(id='algebra', kind='statistical_analysis', definition='A calculated correction is not a checked discrepancy.')]
        case = manifest['cases'][0]
        case['check'] = dict(id=case['id'], kind='statistical_analysis', operation='multiple_testing',
                             p_values=['.01', '.02'], method='holm')
        manifest['cases'] = [case]
        result = run_error_benchmark(manifest)
        self.assertEqual(result['cases'][0]['check_result']['status'], 'CALCULATED')
        self.assertEqual(result['cases'][0]['prediction'], 'abstain')

    def test_manifest_sources_splits_duplicates_and_preflight(self):
        mutations = []
        for key, value in [('papers', []), ('targets', []), ('cases', []), ('dataset_kind', 'expert_verified')]:
            bad = fixture(); bad[key] = value; mutations.append(bad)
        bad = fixture(); bad['papers'][1]['group_id'] = 'g0'; mutations.append(bad)
        bad = fixture(); bad['papers'][1]['sha256'] = '0'*64; mutations.append(bad)
        bad = fixture(); bad['papers'][1].update(text=bad['papers'][0]['text'],sha256=bad['papers'][0]['sha256']); mutations.append(bad)
        bad = fixture(); bad['cases'][0]['source_quote'] = 'absent quote'; mutations.append(bad)
        bad = fixture(); bad['cases'][0]['paper_id'] = 'unknown'; mutations.append(bad)
        bad = fixture(); bad['cases'][0]['check']['text'] = 'override'; mutations.append(bad)
        bad = fixture(); bad['cases'][0]['check']['kind'] = 'derivative'; mutations.append(bad)
        bad = fixture(); bad['cases'][0]['check']['id'] = 'wrong'; mutations.append(bad)
        bad = fixture(); bad['cases'][1]['check']['right'] = '2*x'; mutations.append(bad)
        bad = fixture(); bad['cases'].append(copy.deepcopy(bad['cases'][0])); mutations.append(bad)
        bad = fixture(); bad['targets'].append(dict(id='unused',kind='table_compare',definition='Unused target.')); mutations.append(bad)
        with patch('sra.toolkit._backend', side_effect=AssertionError('backend must not run')):
            for value in mutations:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    run_error_benchmark(value)

    def test_labels_are_complete_separate_and_not_invented_by_template(self):
        manifest = fixture()
        template = error_label_template(manifest)
        self.assertNotIn('prediction', json.dumps(template))
        self.assertTrue(all(r['label'] is None and r['reviewer_id'] is None for c in template['cases'] for r in c['reviewers']))
        predictions = run_error_benchmark(manifest)
        with self.assertRaises(ValueError):
            evaluate_errors(manifest, predictions, template)
        gold = labels(manifest)
        gold['cases'][0]['reviewers'][1]['label'] = 'error'
        with self.assertRaises(ValueError):
            evaluate_errors(manifest, predictions, gold)
        gold['cases'][0]['adjudication'] = dict(reviewer_id='fixture_third', label='no_error', rationale='Synthetic third-party test decision, not actual review.')
        self.assertEqual(evaluate_errors(manifest, predictions, gold)['summary']['confusion']['tn'], 1)
        gold['cases'][0]['adjudication']['reviewer_id'] = 'fixture_a'
        with self.assertRaises(ValueError):
            evaluate_errors(manifest, predictions, gold)

    def test_tampered_predictions_and_label_coverage_fail_closed(self):
        manifest = fixture(); predictions = run_error_benchmark(manifest); gold = labels(manifest)
        invalid = []
        bad = copy.deepcopy(predictions); bad['cases'][0]['prediction'] = 'error'; invalid.append(bad)
        bad = copy.deepcopy(predictions); bad['cases'][0]['source_sha256'] = '0'*64; invalid.append(bad)
        bad = copy.deepcopy(predictions); bad['cases'].pop(); invalid.append(bad)
        bad = copy.deepcopy(predictions); bad['cases'][0]['check_result']['status'] = 'CANDIDATES'; invalid.append(bad)
        for bad in invalid:
            bad['report_sha256'] = fingerprint({k:v for k,v in bad.items() if k!='report_sha256'})
            with self.assertRaises(ValueError):
                evaluate_errors(manifest, bad, gold)
        for modify in [lambda g:g['cases'].pop(),lambda g:g['cases'].append(g['cases'][0]),
                       lambda g:g.update(manifest_sha256='0'*64),lambda g:g.update(label_origin='caller_declared_external')]:
            bad = copy.deepcopy(gold); modify(bad)
            with self.assertRaises(ValueError):
                evaluate_errors(manifest, predictions, bad)

    def test_runtime_metadata_invalid_fingerprints_and_execution_states(self):
        manifest = fixture(); run = run_error_benchmark(manifest); gold = labels(manifest)
        invalid = []
        bad = copy.deepcopy(run); bad['engine'] = []; invalid.append(bad)
        bad = copy.deepcopy(run); bad['engine']['adapter_version'] = 'unknown'; invalid.append(bad)
        bad = copy.deepcopy(run); bad['engine']['source_tree_sha256'] = 'invalid'; invalid.append(bad)
        bad = copy.deepcopy(run); bad['engine']['numerical_environment'] = []; invalid.append(bad)
        bad = copy.deepcopy(run); bad['cases'][0]['check_result']['backend'] = []; invalid.append(bad)
        bad = copy.deepcopy(run); bad['cases'][0]['check_result']['backend_version'] = []; invalid.append(bad)
        bad = copy.deepcopy(run); bad['cases'][0]['check_result']['status'] = 'FAILED'; bad['cases'][0]['prediction'] = 'abstain'; invalid.append(bad)
        for bad in invalid:
            bad['report_sha256'] = fingerprint({k:v for k,v in bad.items() if k!='report_sha256'})
            with self.subTest(engine=bad['engine']), self.assertRaises(ValueError):
                evaluate_errors(manifest, bad, gold)
        bad = copy.deepcopy(run); bad['report_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            evaluate_errors(manifest, bad, gold)

    def test_json_bounds_duplicates_and_malformed_records(self):
        invalid = ['[]','{"x":1,"x":2}',None,{'x':float('nan')},'x'*1048577,
                   '{"x":NaN}','{"v":1e9999999999999999999999999999}',{'schema_version':[]}]
        for value in invalid:
            with self.subTest(value=str(value)[:100]), self.assertRaises(ValueError):
                prepare_manifest(value)
        for category in ('papers','targets','cases'):
            bad = fixture();bad[category][0]['id'] = []
            with self.assertRaises(ValueError):prepare_manifest(bad)
        bad = fixture();bad['papers'][0]['split'] = 'train'
        with self.assertRaises(ValueError):prepare_manifest(bad)
        with self.assertRaises(ValueError):bounded_json({'bad':set()})
        with self.assertRaises(ValueError):canonical_json({1:'non-string key'})
        nested=[]
        for _ in range(66):nested=[nested]
        with self.assertRaises(ValueError):canonical_json(nested)

    def test_real_paper_origin_and_label_boundaries(self):
        manifest=fixture();manifest['dataset_kind']='real_papers'
        # Schema test doubles only, not real-paper evaluation or actual external review.
        gold=labels(manifest);run=run_error_benchmark(manifest)
        self.assertEqual(gold['label_origin'],'caller_declared_external')
        result=evaluate_errors(manifest,run,gold)
        self.assertIn('Real-paper cohort',error_benchmark_markdown(result))
        self.assertFalse(result['reviewer_identity_verified'])
        gold['label_origin']='synthetic_fixture'
        with self.assertRaises(ValueError):evaluate_errors(manifest,run,gold)
        for key,value in [('reviewers',[]),('reviewers',[{'reviewer_id':'same','label':'error','rationale':'A sufficiently long fixture explanation.'}]*2)]:
            bad=labels(manifest);bad['cases'][0][key]=value
            with self.assertRaises(ValueError):evaluate_errors(manifest,run,bad)
        bad=labels(manifest);bad['cases'][0]['reviewers'][0]['rationale']='short'
        with self.assertRaises(ValueError):evaluate_errors(manifest,run,bad)
        bad=copy.deepcopy(run);bad['dataset_id']='another';bad['report_sha256']=fingerprint({k:v for k,v in bad.items() if k!='report_sha256'})
        with self.assertRaises(ValueError):evaluate_errors(manifest,bad,labels(manifest))

    def test_cli_file_bounds_and_report_aliases(self):
        from sra.cli import _reject_input_overwrite,_same_document
        import argparse
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'manifest.json';source.write_text(json.dumps(fixture()))
            with self.assertRaises(ValueError):_read(source,2)
            first=root/'result.json';first.write_text('preserve');os.link(first,root/'result.md')
            args=SimpleNamespace(command='benchmark-errors',input=str(source),out=str(root/'result'))
            with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                execute_error_command(args,argparse.ArgumentParser(),_reject_input_overwrite,_same_document)
            self.assertEqual(first.read_text(),'preserve')

    def test_cli_run_template_evaluate_and_source_overwrite_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); manifest_path=root/'manifest.json';gold_path=root/'labels.json'
            manifest=fixture();manifest_path.write_text(json.dumps(manifest));gold_path.write_text(json.dumps(labels(manifest)))
            def cli(arguments, expected=0):
                with patch('sys.argv',['sra',*map(str,arguments)]),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                    if expected==2:
                        with self.assertRaises(SystemExit) as error:main()
                        self.assertEqual(error.exception.code,2)
                    else:self.assertEqual(main(),expected)
            cli(['benchmark-errors',manifest_path,'--out',root/'run'])
            cli(['error-label-template',manifest_path,'--out',root/'template.json'])
            cli(['evaluate-errors',manifest_path,root/'run.json',gold_path,'--out',root/'evaluation'])
            self.assertEqual(json.loads((root/'evaluation.json').read_text())['summary']['confusion']['tp'],1)
            before=manifest_path.read_bytes()
            cli(['benchmark-errors',manifest_path,'--out',manifest_path],2)
            cli(['error-label-template',manifest_path,'--out',manifest_path],2)
            self.assertEqual(manifest_path.read_bytes(),before)
            alias=root/'hardlink.json';os.link(gold_path,alias)
            cli(['evaluate-errors',manifest_path,root/'run.json',gold_path,'--out',alias],2)
            cli(['benchmark-errors',root/'missing.json','--out',root/'bad'],2)
            with patch('sra.toolkit._backend',side_effect=ImportError('missing')):
                cli(['benchmark-errors',manifest_path,'--out',root/'partial'],1)
            self.assertIn('UNAVAILABLE',(root/'partial.md').read_text())
