"""Deterministic evidence computations are not scientific adequacy decisions."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.document import SourceIdentityError, load_document
from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import digest, prepare_toolkit_spec
from sra.review import review_manuscript
from sra.review_report import review_markdown


TEXT = 'Alpha beta gamma delta epsilon zeta. Planned sample size is 120.'


def snapshot(text):
    return {'text': text, 'sha256': digest(text)}


def checks():
    return [
        {'id': 'overlap', 'kind': 'source_overlap', 'text': TEXT, 'min_tokens': 5,
         'sources': [dict(id='prior', **snapshot('ALPHA beta gamma delta epsilon theta.'))]},
        {'id': 'protocol', 'kind': 'protocol_consistency', 'text': TEXT,
         'protocol': snapshot('Planned sample size is 100.'),
         'fields': [{'id': 'sample_size',
                     'protocol': {'value': '100', 'quote': 'sample size is 100'},
                     'manuscript': {'value': '120', 'quote': 'sample size is 120'}}]},
        {'id': 'checklist', 'kind': 'checklist_evidence', 'text': TEXT,
         'checklist': {'name': 'Synthetic requirements', 'version': '1',
                       'items': [{'id': 'sample', 'requirement': 'Report planned sample size.'},
                                 {'id': 'recruitment', 'requirement': 'Describe recruitment.'}]},
         'assessments': [{'id': 'sample', 'status': 'reported', 'quote': 'sample size is 120'}]},
    ]


def spec(items):
    return {'schema_version': '1.0', 'checks': items}


class EvidenceChecksTests(unittest.TestCase):
    def run_check(self, item):
        return verify_toolkit_spec(spec([item]))['checks'][0]

    def test_actual_computations_and_repeatability(self):
        first = verify_toolkit_spec(spec(checks()))
        self.assertEqual(first, verify_toolkit_spec(spec(checks())))
        overlap, protocol, checklist = first['checks']
        self.assertEqual(overlap['status'], 'CANDIDATES')
        self.assertEqual(overlap['details']['sources'][0]['matched_tokens'], 5)
        self.assertEqual(overlap['details']['sources'][0]['examples'][0]['manuscript']['quote'],
                         'Alpha beta gamma delta epsilon')
        self.assertEqual(protocol['status'], 'REFUTED')
        self.assertEqual(protocol['details']['fields'][0]['comparison'], 'different')
        self.assertEqual(checklist['status'], 'UNDETERMINED')
        self.assertEqual(checklist['details']['unassessed_checks'], ['recruitment'])
        self.assertEqual(first['execution_status'], 'partial')

    def test_bound_document_identity_quotes_and_immutability(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'paper.md'
            path.write_text(TEXT, encoding='utf-8')
            doc = load_document(path)
            items = checks()
            for item in items:
                item.pop('text')
            bound = dict(spec(items), source_sha256=doc.sha256, extracted_text_sha256=digest(doc.text))
            self.assertEqual(len(verify_toolkit_spec(bound, doc)['checks']), 3)
            self.assertEqual(path.read_text(encoding='utf-8'), TEXT)
            for index in range(3):
                bad = copy.deepcopy(bound)
                bad['checks'][index]['text'] = TEXT
                with self.assertRaises(ValueError):
                    prepare_toolkit_spec(bad, doc)
            bad = copy.deepcopy(bound)
            bad['checks'][1]['fields'][0]['manuscript']['quote'] = 'absent'
            with self.assertRaises(SourceIdentityError):
                prepare_toolkit_spec(bad, doc)

    def test_partial_protocol_retains_proven_differences(self):
        item = checks()[1]
        item['fields'].append({'id': 'outcome', 'protocol': None, 'manuscript': None})
        row = self.run_check(item)
        self.assertEqual(row['status'], 'UNDETERMINED')
        self.assertEqual(row['details']['fields'][0]['comparison'], 'different')
        self.assertEqual(row['details']['unassessed_checks'], ['outcome'])
        item['fields'] = item['fields'][:1]
        item['fields'][0]['protocol']['value'] = '120'
        self.assertEqual(self.run_check(item)['status'], 'VERIFIED')

    def test_checklist_exclusions_unknown_and_empty_assessments(self):
        item = checks()[2]
        item['assessments'].append({'id': 'recruitment', 'status': 'not_applicable', 'rationale': 'Simulation only.'})
        row = self.run_check(item)
        self.assertEqual(row['status'], 'CANDIDATES')
        self.assertEqual(row['details']['counts'], {'reported': 1, 'not_applicable': 1, 'unknown': 0, 'unmapped': 0})
        item['assessments'][0] = {'id': 'sample', 'status': 'unknown'}
        self.assertEqual(self.run_check(item)['details']['unassessed_checks'], ['sample'])
        item['assessments'] = []
        self.assertEqual(self.run_check(item)['details']['counts']['unmapped'], 2)

    def test_overlap_union_unicode_short_text_and_output_cap(self):
        item = checks()[0]
        item['text'] = 'Ångström A b c d e f g'
        item['sources'] = [dict(id='s', **snapshot('ångström a b c d e f g'))]
        self.assertEqual(self.run_check(item)['details']['sources'][0]['matched_tokens'], 8)
        item['text'] = 'short'
        short = self.run_check(item)
        self.assertEqual(short['details']['sources'][0]['matched_tokens'], 0)
        self.assertEqual(short['status'], 'UNDETERMINED')
        self.assertEqual(short['details']['unassessed_checks'], ['s'])
        item['text'] = 'a ' * 120
        item['sources'][0].update(snapshot(item['text']))
        row = self.run_check(item)['details']['sources'][0]
        self.assertEqual(row['matched_tokens'], 120)
        self.assertEqual(row['matching_windows'], 116)
        self.assertEqual(len(row['examples']), 100)
        self.assertTrue(row['examples_truncated'])
        item['sources'][0].update(snapshot('entirely unrelated source'))
        self.assertEqual(self.run_check(item)['details']['sources'][0]['matching_windows'], 0)
        self.assertEqual(self.run_check(item)['status'], 'UNDETERMINED')
        item['sources'].append(dict(id='enough', **snapshot('a ' * 10)))
        mixed = self.run_check(item)
        self.assertEqual(mixed['details']['sources'][1]['matched_tokens'], 120)
        self.assertEqual(mixed['details']['unassessed_checks'], ['s'])

    def test_validation_precedes_backend_import(self):
        bad_items = []
        for index, key, value in [(0, 'min_tokens', True), (0, 'min_tokens', 4),
                                  (0, 'sources', []), (0, 'sources', {}),
                                  (1, 'fields', []), (1, 'fields', {}),
                                  (2, 'assessments', {}), (2, 'assessments', [None])]:
            item = checks()[index]
            item[key] = value
            bad_items.append(item)
        item = checks()[0]
        item['sources'][0]['sha256'] = '0' * 64
        bad_items.append(item)
        item = checks()[0]
        item['sources'] *= 2
        bad_items.append(item)
        item = checks()[1]
        item['fields'] *= 2
        bad_items.append(item)
        item = checks()[1]
        item['fields'][0]['protocol']['quote'] = 'absent'
        bad_items.append(item)
        item = checks()[2]
        item['assessments'][0]['quote'] = 'absent'
        bad_items.append(item)
        item = checks()[2]
        item['assessments'][0]['id'] = 'unexpected'
        bad_items.append(item)
        item = checks()[2]
        item['assessments'] *= 2
        bad_items.append(item)
        item = checks()[2]
        item['checklist']['items'] *= 2
        bad_items.append(item)
        item = checks()[2]
        item['assessments'][0] = {'id': 'sample', 'status': 'not_applicable', 'rationale': ''}
        bad_items.append(item)
        item = checks()[2]
        item['assessments'][0]['status'] = 'pass'
        bad_items.append(item)
        with patch('sra.toolkit._backend', side_effect=AssertionError('backend import')):
            for item in bad_items:
                with self.subTest(item=item), self.assertRaises(ValueError):
                    prepare_toolkit_spec(spec([item]))

    def test_overlap_quotes_have_a_character_bound_despite_huge_punctuation_gaps(self):
        item = checks()[0]
        item['text'] = 'a ' * 120
        source = 'a a' + '-' * 90000 + 'a a a'
        item['sources'][0].update(snapshot(source))
        row = self.run_check(item)['details']['sources'][0]
        self.assertEqual(row['matched_tokens'], 120)
        self.assertLess(len(json.dumps(row)), 100000)
        for example in row['examples']:
            quote = example['source']
            self.assertLessEqual(len(quote['quote']), 240)
            self.assertEqual(source[quote['start']:quote['end']], quote['quote'])
            self.assertEqual(quote['window_end'], len(source))
            self.assertTrue(quote['quote_truncated'])

    def test_resource_limits_invalid_ids_and_missing_fields(self):
        invalid = []
        item = checks()[0]
        item['sources'][0]['id'] = []
        invalid.append(item)
        item = checks()[0]
        item['text'] = 'a ' * 20001
        invalid.append(item)
        item = checks()[0]
        item['sources'] = [dict(id=f's{i}', **snapshot('a' * 90000)) for i in range(3)]
        invalid.append(item)
        item = checks()[0]
        item['sources'][0].update(snapshot('a ' * 20001))
        invalid.append(item)
        item = checks()[1]
        item['protocol']['sha256'] = 'bad'
        invalid.append(item)
        item = checks()[1]
        item['fields'][0]['protocol']['value'] = 120
        invalid.append(item)
        item = checks()[2]
        item['checklist']['items'][0]['requirement'] = ''
        invalid.append(item)
        item = checks()[2]
        item['checklist']['items'][0]['extra'] = 'forbidden'
        invalid.append(item)
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ValueError):
                prepare_toolkit_spec(spec([item]))

    def test_unified_matrix_and_cli_deliver_actual_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            paper = Path(directory) / 'paper.md'
            paper.write_text(TEXT, encoding='utf-8')
            document = load_document(paper)
            items = checks()
            for item in items:
                del item['text']
            bound = dict(spec(items), source_sha256=document.sha256,
                         extracted_text_sha256=digest(document.text))
            report = review_manuscript(paper, toolkit_spec=bound, study_type='quantitative')
            rows = {row['id']: row for row in report['criteria_matrix']['criteria']}
            self.assertEqual(rows['registration_and_protocol']['execution_status'], 'checks_completed')
            self.assertEqual(rows['research_integrity']['execution_status'], 'screening_completed')
            self.assertEqual(rows['reporting_guideline_completeness']['execution_status'], 'partial')
            self.assertTrue(all(row['scientific_verdict'] == 'NOT_ASSESSED' for row in rows.values()))
            self.assertIn('caller\\_checklist\\_records\\_only', review_markdown(report))
            path = Path(directory) / 'spec.json'
            path.write_text(json.dumps(spec(checks())), encoding='utf-8')
            output = Path(directory) / 'result'
            result = subprocess.run([sys.executable, '-m', 'sra.cli', 'verify-toolkit', str(path),
                                     '--out', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            delivered = json.loads(output.with_suffix('.json').read_text(encoding='utf-8'))
            self.assertEqual(delivered['checks'][1]['details']['differences'], 1)
