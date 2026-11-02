import argparse
import json
from pathlib import Path

from sra.audit import audit_file, build_review_template
from sra.report import to_markdown
from sra.stats import verify_stats_file


def main() -> int:
    parser = argparse.ArgumentParser(prog="sra", description="Audit scientific manuscript reasoning.")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Run a manuscript reasoning and evidence-graph audit.")
    audit.add_argument("input", help="Path to .md, .txt, or optional .pdf file.")
    audit.add_argument("--out", default="audit-report", help="Output path prefix.")
    audit.add_argument("--semantic-review", default=None, help="Optional JSON completed by an external semantic reviewer/agent.")

    template = sub.add_parser("review-template", help="Create a source-bound template for an external semantic reviewer.")
    template.add_argument("input", help="Path to the manuscript already audited by SRA.")
    template.add_argument("--out", default="semantic-review-template.json", help="Output JSON path.")

    stats = sub.add_parser("verify-stats", help="Independently recalculate supported statistical summaries.")
    stats.add_argument("input", help="JSON input; currently supports test=welch_t.")
    stats.add_argument("--out", default="stats-verification.json", help="Output JSON path.")

    args = parser.parse_args()
    if args.command == "audit":
        try:
            report = audit_file(args.input, args.semantic_review)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            parser.error(str(exc))
        prefix = Path(args.out)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        json_path, md_path = prefix.with_suffix(".json"), prefix.with_suffix(".md")
        json_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(to_markdown(report), encoding="utf-8")
        graph = report.reasoning_graph
        print(f"Audit complete: {len(report.findings)} findings; {len(report.claim_evidence_candidates)} extracted claims; {len(graph.get('nodes', []))} graph nodes and {len(graph.get('edges', []))} graph edges.")
        if report.semantic_review:
            print(f"Semantic review import: {report.semantic_review['status']}")
            if report.semantic_review["errors"]:
                print(f"Semantic review validation errors: {len(report.semantic_review['errors'])}")
        print(f"JSON: {json_path.resolve()}")
        print(f"Markdown: {md_path.resolve()}")
        return 2 if report.semantic_review and report.semantic_review["status"] == "REJECTED" else 0

    if args.command == "review-template":
        try:
            result = build_review_template(args.input)
        except (OSError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Semantic review template created for {len(result['assessments'])} inference(s).")
        print(f"Template: {output.resolve()}")
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
