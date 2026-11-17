"""Presentation must preserve scientific results, evidence and uncertainty."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.review import review_manuscript
from sra.review_report import review_markdown
from sra.report import _safe_md


class ReportStyleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paper = Path(self.tmp.name) / 'paper.md'
        self.paper.write_text('# Methods\nWe measure a distance in meters.\n# Results\nThe value is 3.\n')

    def test_real_results_evidence_and_source_survive_both_styles_without_mutation(self):
        example = Path(__file__).parents[1] / 'examples/welch_t_example.json'
        report = review_manuscript(self.paper, disciplines=['physics'], statistics_spec=json.loads(example.read_text()))
        before = copy.deepcopy(report)
        original = self.paper.read_bytes()
        natural = review_markdown(report)
        technical = review_markdown(report, style='technical')
        self.assertEqual(report, before)
        self.assertEqual(self.paper.read_bytes(), original)
        self.assertEqual(report['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(natural, review_markdown(report))
        self.assertLess(len(natural), len(technical))
        self.assertIn('Requested checks finished.', natural)
        self.assertIn('not the scientific validity', natural)
        self.assertNotIn('Required evidence:**', natural)
        self.assertIn('Required evidence:**', technical)
        for text in (natural, technical):
            self.assertIn(report['source_sha256'], text)
            self.assertIn('NOT_ASSESSED', text)
            for row in report['criteria_matrix']['criteria']:
                self.assertIn(_safe_md(row['title']), text)
            for item in report['modules']['discipline:physics']['result']['items']:
                for evidence in item['evidence']:
                    self.assertIn(_safe_md(evidence['excerpt']), text)
                    self.assertIn(f"Line {evidence['line']}", text)
            serialized = json.dumps(report['modules']['statistics']['result'], ensure_ascii=False, indent=2, allow_nan=False)
            self.assertIn(serialized, text)
        self.assertIn('UNDETERMINED', natural)

    def test_real_conditional_logic_verdicts_and_abstention_remain_explicit(self):
        from sra.document import load_document
        doc = load_document(self.paper)
        spec = json.loads((Path(__file__).parents[1] / 'examples/logic_boolean.json').read_text())
        spec.update(source_sha256=doc.sha256,
                    extracted_text_sha256=hashlib.sha256(doc.text.encode()).hexdigest())
        report = review_manuscript(self.paper, logic_spec=spec)
        logic = report['modules']['logic']['result']
        self.assertEqual([row['status'] for row in logic['claims']],
                         ['VERIFIED', 'REFUTED', 'UNDETERMINED'])
        for style in ('natural', 'technical'):
            text = review_markdown(report, style=style)
            self.assertIn('conditional on the supplied formulas and assumptions', text)
            for row in logic['claims']:
                self.assertIn(f"### {row['id']}: {row['status']}", text)
                self.assertIn(_safe_md(row['expression']), text)
            self.assertIn(logic['report_sha256'], text)
        self.assertIn('can be either true or false', review_markdown(report))

    def test_partial_unavailable_failed_and_unrequested_are_not_success(self):
        for error, state in ((ImportError(), 'unavailable'), (RuntimeError(), 'failed')):
            with patch('sra.review.review_domain', side_effect=error):
                report = review_manuscript(self.paper, disciplines=['physics'])
            text = review_markdown(report)
            self.assertIn('Some requested checks did not finish.', text)
            self.assertNotIn('Requested checks finished.', text)
            self.assertIn(f'({state})', text)
            self.assertIn('not\\_requested', text)
        report['modules']['other'] = dict(status='partial', reason='Only part ran.', result=None)
        report['modules']['excluded'] = dict(status='not_applicable', reason='', result=None)
        text = review_markdown(report)
        self.assertIn('Inspect this module', text)
        self.assertIn('Excluded by the declared study type', text)

    def test_safe_untrusted_cells_fences_and_old_reports_without_matrix(self):
        report = review_manuscript(self.paper, study_type='theoretical')
        report['source'] = '<script>alert(1)</script>\n# Fake'
        report['criteria_matrix']['criteria'][0]['title'] = 'A | <img src=x onerror=bad>'
        report['modules']['extraction']['result']['hostile'] = '````\n<script>bad</script>'
        text = review_markdown(report)
        self.assertNotIn('<script>', text.split('`````json')[0])
        self.assertIn('A &#124; &lt;img', text)
        self.assertIn('`````json\n', text)
        self.assertIn('\\# Fake', text)
        report.pop('criteria_matrix')
        report['excluded_findings'] = []
        self.assertIn('No findings were excluded', review_markdown(report))
        self.assertIn('No findings were excluded', review_markdown(report, style='technical'))
        for style in ('auto', None, 3, ['natural']):
            with self.assertRaises(ValueError):
                review_markdown(report, style=style)
