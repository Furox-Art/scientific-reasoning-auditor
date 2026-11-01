import argparse
import json
from pathlib import Path

from sra.audit import audit_file
from sra.report import to_markdown


def main() -> int:
    parser = argparse.ArgumentParser(prog="sra", description="Screen a scientific manuscript.")
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit", help="Run a deterministic first-pass audit.")
    audit.add_argument("input", help="Path to .md, .txt, or optional .pdf file.")
    audit.add_argument("--out", default="audit-report", help="Output path prefix.")
    args = parser.parse_args()
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


if __name__ == "__main__":
    raise SystemExit(main())
