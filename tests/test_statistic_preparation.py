"""Source notation recovery controls, never scientific error gold labels."""
import hashlib
import unittest

from sra.document import parse_document_text
from sra.inspection import prepare_inspection
from sra.toolkit import verify_toolkit_spec


def prepare(text):
    document = parse_document_text(text, source='paper.md', sha256=hashlib.sha256(text.encode()).hexdigest())
    return prepare_inspection(document)


class LiteralStatisticTests(unittest.TestCase):
    def drafts(self, report):
        return [c for c in report['candidates'] if c.get('suggested_check') is not None]

    def test_real_source_order_separate_df_and_uppercase_p(self):
        text = ('First (X^(2) = 7.66, df = 2, P = 0.02), followed by '
                '(X^(2) = 11.54, df = 2, P < 0.01).\n'
                'Finally (X^(2) = 4.72, df = 2, P = 0.10; Fig 3).')
        report = prepare(text)
        rows = self.drafts(report)
        self.assertEqual([r['suggested_check']['statistic'] for r in rows], ['7.66', '11.54', '4.72'])
        self.assertEqual([r['suggested_check']['relation'] for r in rows], ['=', '<', '='])
        self.assertFalse(report['checks_executed'])
        for row in rows:
            self.assertEqual(text[row['start']:row['end']], row['source_quote'])
            self.assertEqual(row['line'], text.count('\n', 0, row['start']) + 1)
            self.assertTrue(row['requires_confirmation'])
            self.assertEqual(row['suggested_check']['test'], 'chi2')
            self.assertEqual(row['suggested_check']['df'], [2])
            self.assertEqual(row['suggested_check']['alternative'], 'unknown')
            self.assertEqual(row['suggested_check']['df_precision'], 'unknown')

    def test_common_chi_notation_is_a_reference_draft_not_test_identification(self):
        for label in ('χ²', 'χ2', 'χ^2', 'χ^(2)', 'X²', 'X^2', 'chi2', 'CHI2'):
            with self.subTest(label=label):
                rows = self.drafts(prepare(label + '(2) = 7.66, P = .02'))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['suggested_check']['test'], 'chi2')

    def test_multiple_tests_minus_signs_fractional_df_and_no_cross_line_linking(self):
        text = 'T(10.50) = −2.40, P = .03; F = 4.50, df = 1, 20, p < .05; Z = 2.00, P > .01'
        checks = [r['suggested_check'] for r in self.drafts(prepare(text))]
        self.assertEqual([r['test'] for r in checks], ['t', 'F', 'z'])
        self.assertEqual(checks[0]['df'], ['10.50'])
        self.assertEqual(checks[0]['statistic'], '-2.40')
        self.assertEqual(checks[1]['df'], [1, 20])
        self.assertEqual(checks[2]['df_precision'], 'exact')
        self.assertFalse(self.drafts(prepare('t(12) = 2.4\np = .03')))

    def test_ambiguous_or_invalid_values_remain_candidates_without_drafts(self):
        for text in ('t = 2.4, P = .03', 'F(12) = 2.4, P = .03',
                     't(12) = 2.4, df = 10, P = .03',
                     't(0) = 2.4, P = .03', 't(1e100) = 2.4, P = .03',
                     't(12) = 2.4, P = 1.2', 't(12) = 2.4, P = 0,03',
                     't(12) = 2.4, P = .03abc', 't(12) = 2.4, P ≤ .03',
                     'r = .4, P = .03', 'prefixchi2(2) = 7.66, P = .02'):
            with self.subTest(text=text):
                report = prepare(text)
                self.assertFalse(self.drafts(report))

    def test_unsupported_p_in_same_paragraph_stays_visible(self):
        text = 't(12) = 2.400, P = .03. Another analysis had P = .07.'
        rows = prepare(text)['candidates']
        self.assertEqual(len(self.drafts({'candidates': rows})), 1)
        unresolved = [r for r in rows if r['kind'] == 'statistic' and r['suggested_check'] is None]
        self.assertEqual(len(unresolved), 1)
        self.assertIn('P = .07', unresolved[0]['source_quote'])

    def test_code_fences_batching_and_extraction_limits(self):
        report = prepare('```\nX²(2) = 7.66, P = .02\n```\n' + 'X²(2) = 7.66, P = .02; ' * 33)
        self.assertEqual([len(b['checks']) for b in report['proposed_toolkit_specs']], [32, 1])
        self.assertEqual(len(self.drafts(report)), 33)
        with self.assertRaises(ValueError):
            prepare('X²(2) = 7.66, P = .02; ' * 501)

    def test_explicit_execution_of_unconfirmed_drafts_abstains(self):
        report = prepare('X²(2) = 7.66, P = .02; F(1, 20) = 4.50, P < .05')
        self.assertEqual(len(report['proposed_toolkit_specs']), 1)
        result = verify_toolkit_spec(report['proposed_toolkit_specs'][0])
        self.assertEqual([c['status'] for c in result['checks']], ['UNDETERMINED', 'UNDETERMINED'])

    def test_whitespace_and_unsupported_numeric_suffixes_do_not_fabricate_values(self):
        self.assertFalse(self.drafts(prepare('t' + ' ' * 10000 + '!')))
        for suffix in ('.4', '.abc', 'e100', ',03'):
            self.assertFalse(self.drafts(prepare('t(12) = 2.40, P = .03' + suffix)))


if __name__ == '__main__':
    unittest.main()
