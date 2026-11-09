"""Numbers printed in a table become statements the audit can read."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pdf_table_fixture import table_pdf
from sra.audit import audit_file
from sra.tabular_values import table_findings, table_statements

TABLE = (
    "# Results\n"
    "Group             n            mean            SD               p\n"
    "A                 12           4.1             3.2              0.03\n"
    "C                 10           -0.4            -1.2             0.000\n"
)


class TableStatementTests(unittest.TestCase):
    def test_a_header_and_rows_produce_column_statements(self):
        statements = [item[0] for item in table_statements(TABLE)]
        self.assertEqual(
            statements,
            ["n = 12", "SD = 3.2", "p = 0.03", "n = 10", "SD = -1.2", "p = 0.000"],
        )

    def test_rows_without_a_header_are_ignored(self):
        self.assertEqual(table_statements("A    12    4.1"), [])

    def test_a_row_with_the_wrong_cell_count_is_ignored(self):
        text = "n    SD\n12    3.2    9.9\n"
        self.assertEqual(table_statements(text), [])

    def test_unknown_columns_are_ignored(self):
        text = "site    batch\nA       7\n"
        self.assertEqual(table_statements(text), [])

    def test_a_non_numeric_cell_is_ignored(self):
        # "many" is not a number, so the n column yields nothing; the SD cell in
        # the same row is still a number and is still read.
        text = "n    SD\nmany   3.2\n"
        self.assertEqual([item[0] for item in table_statements(text)], ["SD = 3.2"])

    def test_a_single_column_line_ends_the_table(self):
        text = "n    SD\n12   3.2\nnotes\n12   4.0\n"
        self.assertEqual([item[0] for item in table_statements(text)], ["n = 12", "SD = 3.2"])


class TableFindingTests(unittest.TestCase):
    def test_an_impossible_value_in_a_cell_is_reported(self):
        findings = table_findings(TABLE)
        check_ids = {finding.check_id for finding in findings}
        self.assertEqual(
            check_ids,
            {"statistics.impossible_dispersion", "statistics.impossible_p_value"},
        )
        for finding in findings:
            self.assertEqual(finding.evidence_locations[0]["kind"], "table_cell")
            self.assertIn("table column", finding.evidence[0])

    def test_an_ordinary_table_is_silent(self):
        text = "n    SD\n12   3.2\n10   1.4\n"
        self.assertEqual(table_findings(text), [])


class PdfTableTests(unittest.TestCase):
    def test_a_pdf_table_is_read_and_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = table_pdf(Path(folder) / "table.pdf")
            report = audit_file(str(path))
        check_ids = {finding.check_id for finding in report.findings}
        self.assertIn("statistics.impossible_dispersion", check_ids)
        self.assertIn("statistics.impossible_p_value", check_ids)
        self.assertEqual(report.reproducibility_manifest["input"]["format"], "pdf")
        self.assertEqual(
            report.reproducibility_manifest["parser"]["backend"], "pypdf-layout"
        )


if __name__ == "__main__":
    unittest.main()
