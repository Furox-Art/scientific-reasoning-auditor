import argparse
import json
from pathlib import Path

from sra.audit import audit_file, audit_parsed_document, build_review_template
from sra.document import load_document
from sra.model_client import request_single_model_review
from sra.semantic_review import build_semantic_review_template, validate_semantic_review
from sra.report import to_markdown
from sra.stats import verify_stats_file
from sra.scientific_validation import verify_scientific_file


def _reject_input_overwrite(
    parser: argparse.ArgumentParser,
    input_paths: list[str | None],
    output_paths: list[Path],
) -> None:
    """Fail before reads, network requests or writes on resolved path collisions.

    Resolving symlinks prevents accidental source clobbering through output
    aliases. This is a local preflight check, not a defence against concurrent
    filesystem modifications by a hostile process.
    """
    try:
        protected = {
            Path(name).resolve(strict=False) for name in input_paths if name
        }
        if any(path.resolve(strict=False) in protected for path in output_paths):
            parser.error(
                "Output path would overwrite an input or imported review file; choose a different --out."
            )
    except (OSError, RuntimeError):
        parser.error("Could not safely resolve input/output paths.")



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
    template.add_argument(
        "--mode",
        choices=("single", "parallel"),
        default="single",
        help="Choose one model (single) or parallel agents (parallel).",
    )

    model_review = sub.add_parser("review-model", help="Run a single-model semantic review through an OpenAI-compatible API.")
    model_review.add_argument("input", help="Path to the manuscript.")
    model_review.add_argument("--model", required=True, help="Model identifier accepted by the configured endpoint.")
    model_review.add_argument("--base-url", default="https://api.openai.com/v1", help="OpenAI-compatible API base URL.")
    model_review.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Environment variable containing the API key.")
    model_review.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds.")
    model_review.add_argument("--out", default="semantic-review-completed.json", help="Output JSON path.")

    stats = sub.add_parser("verify-stats", help="Independently recalculate supported statistical summaries.")
    stats.add_argument("input", help="JSON input; currently supports test=welch_t.")
    stats.add_argument("--out", default="stats-verification.json", help="Output JSON path.")

    science = sub.add_parser(
        "verify-science",
        help="Validate explicitly structured CI claims, SI-dimension equations, and crude risk ratios.",
    )
    science.add_argument("input", help="Bounded JSON scientific-check specification.")
    science.add_argument("--out", default="science-verification.json", help="Output JSON path.")

    args = parser.parse_args()
    if args.command == "audit":
        prefix = Path(args.out)
        outputs = [prefix.with_suffix(".json"), prefix.with_suffix(".md")]
        inputs = [args.input, args.semantic_review]
    elif args.command == "review-model":
        output = Path(args.out)
        outputs = [output, output.with_name(output.stem + ".provenance.json")]
        inputs = [args.input]
    else:
        outputs = [Path(args.out)]
        inputs = [args.input]
    _reject_input_overwrite(parser, inputs, outputs)
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
            result = build_review_template(args.input, review_mode=args.mode)
        except (OSError, ValueError, RuntimeError) as exc:
            parser.error(str(exc))
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Semantic review template created for {len(result['assessments'])} inference(s).")
        print(f"Review mode: {result['review_mode']}")
        print(f"Template: {output.resolve()}")
        return 0

    if args.command == "review-model":
        try:
            document = load_document(args.input)
            report = audit_parsed_document(document)
            template = build_semantic_review_template(
                report.to_dict(), review_mode="single", source_text=document.text
            )
            provenance = {
                "source_sha256": report.to_dict().get("sha256"),
                "graph_fingerprint": report.to_dict().get("reasoning_graph", {}).get("graph_fingerprint"),
            }
            completed = request_single_model_review(
                template, document.text, model=args.model, base_url=args.base_url,
                api_key_env=args.api_key_env, timeout=args.timeout,
                provenance=provenance,
            )
            validation = validate_semantic_review(
                completed, report.to_dict(), document.text
            )
            serialized_completed = json.dumps(
                completed, ensure_ascii=False, indent=2, allow_nan=False
            )
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError, TypeError) as exc:
            parser.error(str(exc))
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized_completed, encoding="utf-8")
        provenance_path = output.with_name(output.stem + ".provenance.json")
        provenance_path.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        print(f"Model review saved: {output.resolve()}")
        print(f"Model request provenance: {provenance_path.resolve()}")
        print(f"Structural validation: {validation['status']}")
        for error in validation["errors"]:
            print(f"- {error}")
        print("Structural acceptance does not prove semantic correctness.")
        return 0 if validation["status"] == "ACCEPTED_FOR_REVIEW" else 2

    try:
        result = (verify_scientific_file(args.input)
                  if args.command == "verify-science"
                  else verify_stats_file(args.input))
        serialized_result = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    except (OSError, ValueError, RuntimeError, ArithmeticError, TypeError) as exc:
        parser.error(str(exc))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized_result, encoding="utf-8")
    print(f"{'Scientific' if args.command == 'verify-science' else 'Statistics'} verification status: {result['status']}")
    print(f"Result: {output.resolve()}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
