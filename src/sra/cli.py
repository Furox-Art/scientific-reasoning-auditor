import argparse
import json
from pathlib import Path

from sra.audit import audit_file
from sra.report import to_markdown
from sra.stats import verify_stats_file


def main() -> int:
    parser = argparse.ArgumentParser(prog="sra", description="Audit scientific manuscript reasoning.")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Run a deterministic manuscript reasoning screen.")
    audit.add_argument("input", help="Path to .md, .txt, or optional .pdf file.")
    audit.add_argument("--out", default="audit-report", help="Output path prefix.")

    stats = sub.add_parser("verify-stats", help="Independently recalculate supported statistical summaries.")
    stats.add_argument("input", help="JSON input; currently supports test=welch_t.")
    stats.add_argument("--out", default="stats-verification.json", help="Output JSON path.")

    args = parser.parse_args()
    if args.command == "audit":
        report = audit_file(args.input)
        prefix = Path(args.out)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        json_path, md_path = prefix.with_suffix(".json"), prefix.with_suffix(".md")
        json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(to_markdown(report), encoding="utf-8")
        print(f"Audit complete: {len(report.findings)} findings; "
              f"{len(report.claim_evidence_candidates)} claim-evidence candidates.")
        print(f"JSON: {json_path.resolve()}")
        print(f"Markdown: {md_path.resolve()}")
        return 0

    try:
        result = verify_stats_file(args.input)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Statistics verification status: {result['status']}")
    print(f"Result: {output.resolve()}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
