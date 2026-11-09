"""Every finding the audit can emit must be documented, and vice versa.

The inventory next to this test is only useful if it cannot drift, so the build
compares the two sides: a rule added without a row fails, and a row left behind
after a rule is removed fails too. Each row must also say what the rule cannot
see and where its false positives come from; a row that only restates the rule
is rejected.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "CHECK_INVENTORY.md"
SOURCE = ROOT / "src" / "sra"

RULE_NAME = re.compile(r"^[a-z_]+\.[a-z_]+$")
ROW = re.compile(r"^\|\s*`(?P<id>[a-z_]+\.[a-z_]+)`\s*\|(?P<cells>.*)\|\s*$")

#: A cell has to carry a real explanation, not a restatement of the heading.
MINIMUM_CELL_CHARS = 25


def rule_ids_in_source() -> set[str]:
    """Every check id passed as the first argument of a finding constructor."""
    found: set[str] = set()
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in {"Finding", "_finding"}:
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if RULE_NAME.match(first.value):
                    found.add(first.value)
    return found


def inventory_rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match is None:
            continue
        cells = [cell.strip() for cell in match.group("cells").split("|")]
        rows[match.group("id")] = cells
    return rows


class CheckInventoryTests(unittest.TestCase):
    def test_every_rule_is_documented(self):
        documented = set(inventory_rows())
        implemented = rule_ids_in_source()
        self.assertTrue(implemented, "no rules found: the audit would pass vacuously")
        self.assertEqual(
            sorted(implemented - documented),
            [],
            "rules exist without an inventory row; document them in docs/CHECK_INVENTORY.md",
        )

    def test_every_documented_rule_still_exists(self):
        documented = set(inventory_rows())
        implemented = rule_ids_in_source()
        self.assertEqual(
            sorted(documented - implemented),
            [],
            "the inventory lists rules the audit can no longer emit",
        )

    def test_each_row_says_what_it_cannot_see_and_where_it_misfires(self):
        for rule, cells in inventory_rows().items():
            with self.subTest(rule=rule):
                self.assertEqual(len(cells), 3, f"{rule}: expected three columns")
                detects, cannot, misfires = cells
                for label, cell in (
                    ("detects", detects),
                    ("cannot detect", cannot),
                    ("false positive", misfires),
                ):
                    self.assertGreaterEqual(
                        len(cell), MINIMUM_CELL_CHARS, f"{rule}: {label} cell is too thin"
                    )


if __name__ == "__main__":
    unittest.main()
