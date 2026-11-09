"""Run the synthetic rule ablation and write benchmarks/rule_ablation/report.json."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sra.rule_ablation import evaluate_rule_corpus  # noqa: E402

CORPUS = ROOT / "benchmarks" / "rule_ablation"


def rule_ids() -> list[str]:
    ids: set[str] = set()
    for path in sorted((ROOT / "src" / "sra").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in {"Finding", "_finding"} or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if "." in first.value:
                    ids.add(first.value)
    return sorted(ids)


def main() -> int:
    report = evaluate_rule_corpus(CORPUS / "cases.json", rule_ids())
    target = CORPUS / "report.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(
        f"{summary['exercised']}/{summary['rules']} rules exercised, "
        f"missed {len(summary['missed_planted'])}, "
        f"never fired {len(summary['never_fired'])}, "
        f"false positives {len(summary['with_false_positive'])}"
    )
    print(f"wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
