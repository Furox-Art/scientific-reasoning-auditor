"""Regression checks for manuscript parsing and unambiguous statistics inputs."""
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sra.audit import audit_file
from sra.document import _split_sections, load_document, without_fenced_code
from sra.stats import verify_stats_file


class MarkdownFenceIntegrityTests(unittest.TestCase):
    def test_indented_closing_fences_preserve_following_sections(self):
        # CommonMark permits zero to three leading spaces before a fence.
        # Opening and closing indentation need not be identical.
        for opener_indent in range(4):
            for closer_indent in range(4):
                with self.subTest(open=opener_indent, close=closer_indent):
                    manuscript = (
                        "# Methods\n"
                        "Methods text.\n"
                        + " " * opener_indent + "```python\n"
                        + "# Fabricated Results\n"
                        + "direction = 'increased'\n"
                        + " " * closer_indent + "```   \n"
                        + "# Results\n"
                        + "Observed outcome decreased.\n"
                        + "# Conclusion\n"
                        + "The outcome decreased.\n"
                    )
                    cleaned = without_fenced_code(manuscript)
                    sections, start_lines = _split_sections(manuscript)
                    self.assertEqual(
                        list(sections), ["Methods", "Results", "Conclusion"]
                    )
                    self.assertEqual(sections["Methods"], "Methods text.")
                    self.assertEqual(sections["Results"], "Observed outcome decreased.")
                    self.assertEqual(start_lines["Results"], 8)
                    self.assertEqual(start_lines["Conclusion"], 10)
                    self.assertNotIn("Fabricated Results", cleaned)
                    self.assertNotIn("direction =", cleaned)
                    self.assertEqual(cleaned.count("\n"), manuscript.count("\n"))

    def test_full_audit_retains_results_after_indented_fence(self):
        text = (
            "# Methods\n"
            "The experiment compared group outcomes.\n"
            "  ```python\n"
            "# Conclusion\n"
            "This is a code comment, not a scientific conclusion.\n"
            "  ```\n"
            "# Results\n"
            "The measured outcome decreased.\n"
            "# Conclusion\n"
            "The measured outcome decreased.\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manuscript.md"
            path.write_text(text, encoding="utf-8")
            document = load_document(path)
            report = audit_file(str(path))
            self.assertEqual(
                list(document.sections), ["Methods", "Results", "Conclusion"]
            )
            self.assertEqual(report.section_names, ["Methods", "Results", "Conclusion"])
            self.assertEqual(document.section_start_lines["Results"], 8)

    def test_tilde_fences_with_indentation_hide_fake_headings(self):
        manuscript = (
            "# Methods\n"
            "  ~~~~ r\n"
            "# Hidden Conclusion\n"
            "   ~~~~\n"
            "# Results\n"
            "Measured effect.\n"
        )
        sections, lines = _split_sections(manuscript)
        self.assertEqual(list(sections), ["Methods", "Results"])
        self.assertEqual(lines["Results"], 6)
        self.assertEqual(sections["Results"], "Measured effect.")


class StatisticsInputIntegrityTests(unittest.TestCase):
    BASE = (
        '{"test":"welch_t","group_a":{"mean":5,"sd":1,"n":25},'
        '"group_b":{"mean":4,"sd":1,"n":25},"reported":{"t":3.5}}'
    )

    def test_duplicate_keys_rejected_at_all_nesting_levels(self):
        cases = {
            "top_level": self.BASE.replace(
                '"test":"welch_t"', '"test":"welch_t","test":"welch_t"'
            ),
            "sample_size": self.BASE.replace('"n":25', '"n":25,"n":26'),
            "reported_statistic": self.BASE.replace('"t":3.5', '"t":3.5,"t":0.0'),
            "escaped_equivalent": self.BASE.replace(
                '"n":25', '"n":25,"\\u006e":26'
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stats.json"
            for name, payload in cases.items():
                with self.subTest(case=name):
                    path.write_text(payload, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
                        verify_stats_file(path)

    def test_cli_does_not_write_report_from_ambiguous_json(self):
        duplicate = self.BASE.replace('"n":25', '"n":25,"n":50')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stats.json"
            output = Path(tmp) / "stats-report.json"
            path.write_text(duplicate, encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, "-m", "sra.cli", "verify-stats",
                    str(path), "--out", str(output),
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Duplicate JSON key", result.stderr)
            self.assertFalse(output.exists())

    def test_distinct_keys_in_different_groups_are_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stats.json"
            path.write_text(self.BASE, encoding="utf-8")
            result = verify_stats_file(path)
            self.assertEqual(
                result["input_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
            self.assertEqual(result["status"], "PASS")  # 3.5 ± 0.05 contains 3.5355...
            self.assertEqual(
                result["inputs"]["group_a"]["n"],
                result["inputs"]["group_b"]["n"],
            )


if __name__ == "__main__":
    unittest.main()
