import argparse
import json
import os
from pathlib import Path

from sra.audit import audit_file, audit_parsed_document, build_review_template
from sra.document import load_document
from sra.model_client import request_single_model_review
from sra.paper_review import review_paper, paper_review_markdown
from sra.semantic_review import build_semantic_review_template, validate_semantic_review
from sra.report import to_markdown
from sra.stats import verify_stats_file
from sra.writing import audit_academic_writing, writing_report_markdown
from sra.doi import verify_dois
from sra.benchmark import run_pmc_benchmark
from sra.discipline import CHECKLISTS
from sra.validation import evaluate_blinded_labels
from sra.labeling import build_validation_pack, merge_adjudicated_labels
from sra.domain_evidence import PROFILES, audit_domain_file
from sra.domain_adjudication import make_domain_template, validate_domain_adjudication
from sra.academic_benchmark import evaluate_arxiv_edit_pairs
from sra.domain_cohort import aggregate_domain_reports
from sra.scientific_validation import verify_scientific_file
from sra.review import review_manuscript
from sra.unified_cli import configure_review_commands, execute_review_command
from sra.logic_cli import configure_logic_commands, execute_logic_command
from sra.toolkit_cli import configure_toolkit_commands, execute_toolkit_command


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
        inputs = [Path(name).expanduser() for name in input_paths if name]
        protected = {path.resolve(strict=False) for path in inputs}
        for output in output_paths:
            if output.resolve(strict=False) in protected:
                parser.error(
                    "Output path would overwrite an input or imported review file; choose a different --out."
                )
            # A hard link is a second name for the same inode and resolves to its
            # own path, so the resolved-path set above cannot see it. Writing the
            # "output" would still destroy the input, so compare identities.
            if any(_same_document(output, path) for path in inputs):
                parser.error(
                    "Output path would overwrite an input or imported review file; choose a different --out."
                )
    except (OSError, RuntimeError):
        parser.error("Could not safely resolve input/output paths.")


def _same_document(left: Path, right: Path) -> bool:
    """True when two paths reach the same file, through symlinks or hard links.

    Comparing ``resolve()`` strings only catches symlinks: a hard link is a
    second name for the same inode and resolves to a different path, so writing
    the "output" would have overwritten the manuscript it was auditing.
    ``samefile`` compares the file identity; it needs both paths to exist, which
    is exactly the case that matters here.
    """
    try:
        return os.path.samefile(left, right)
    except OSError:
        return left.resolve() == right.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(prog="sra", description="Audit scientific manuscript reasoning.")
    sub = parser.add_subparsers(dest="command", required=True)
    configure_review_commands(sub)
    configure_logic_commands(sub)
    configure_toolkit_commands(sub)

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

    paper = sub.add_parser("paper-review", help="Read all extracted paper text, explain it in detail, and critique scientific claims using a model.")
    paper.add_argument("input", help="Paper .md, .txt or optional .pdf file.")
    paper.add_argument("--model", required=True, help="OpenAI-compatible model identifier.")
    paper.add_argument("--base-url", default="https://api.openai.com/v1")
    paper.add_argument("--api-key-env", default="OPENAI_API_KEY")
    paper.add_argument("--timeout", type=int, default=120)
    paper.add_argument("--chunk-chars", type=int, default=12000)
    paper.add_argument("--ocr-mode", choices=("off", "missing", "all"), default="missing")
    paper.add_argument("--ocr-languages", default="eng", help="Installed Tesseract language codes, e.g. eng+tur.")
    paper.add_argument("--visual-pages", action="store_true", help="Opt-in: send each PDF page image to the selected vision-capable model.")
    paper.add_argument("--out", default="paper-review", help="JSON and Markdown output prefix.")

    stats = sub.add_parser("verify-stats", help="Independently recalculate supported statistical summaries.")
    stats.add_argument("input", help="JSON input for Welch, one-sample/paired t, two-proportion z, chi-square or Fisher exact.")
    stats.add_argument("--out", default="stats-verification.json", help="Output JSON path.")

    writing = sub.add_parser(
        "writing-audit", help="Review academic structure and citation consistency."
    )
    writing.add_argument("input", help="Manuscript .md, .txt, or optional .pdf file.")
    writing.add_argument("--out", default="academic-writing-report", help="Output path prefix.")
    writing.add_argument(
        "--genre", choices=("general", "original-research"), default="general",
        help="Use optional original-research section checklist.",
    )
    writing.add_argument("--abstract-min-words", type=int, default=None)
    writing.add_argument("--abstract-max-words", type=int, default=None)
    writing.add_argument("--style-language", choices=("en", "tr", "none"), default="en")
    writing.add_argument("--design", choices=tuple(CHECKLISTS), default=None,
                         help="Optional study-design reporting cues (not formal compliance).")
    writing.add_argument("--discipline", choices=tuple(PROFILES), default=None,
                         help="Source-located discipline-specific evidence prompts.")
    writing.add_argument(
        "--grammar-engine", choices=("rules", "local-languagetool"), default="rules",
        help="Optional local-only LanguageTool service (no cloud API calls).",
    )
    writing.add_argument("--grammar-port", type=int, default=8081)
    writing.add_argument("--grammar-timeout", type=float, default=8.0)

    domain_review = sub.add_parser(
        "domain-review", help="Paragraph-grounded discipline reporting cues, not expert verdicts."
    )
    domain_review.add_argument("input")
    domain_review.add_argument("--discipline", choices=tuple(PROFILES), required=True)
    domain_review.add_argument("--out", default="domain-review.json")

    domain_template = sub.add_parser(
        "domain-template", help="Export a source-bound template for two external experts."
    )
    domain_template.add_argument("input")
    domain_template.add_argument("--discipline", choices=tuple(PROFILES), required=True)
    domain_template.add_argument("--out", default="domain-template.json")

    domain_validate = sub.add_parser(
        "domain-validate", help="Check completed external expert assessments and source quotes."
    )
    domain_validate.add_argument("input")
    domain_validate.add_argument("assessments")
    domain_validate.add_argument("--discipline", choices=tuple(PROFILES), required=True)
    domain_validate.add_argument("--out", default="domain-adjudication.json")

    doi = sub.add_parser("doi-check", help="Extract DOIs and optionally check Crossref registry metadata.")
    doi.add_argument("input", help="Manuscript path.")
    doi.add_argument("--out", default="doi-check.json")
    doi.add_argument("--online", action="store_true",
                     help="Explicitly enable network metadata requests to Crossref.")
    doi.add_argument("--limit", type=int, default=50)

    benchmark = sub.add_parser("benchmark-pmc", help="Run external PMC BioC real-paper smoke tests.")
    benchmark.add_argument("manifest", help="JSON manifest with pmcids list.")
    benchmark.add_argument("--out", default="pmc-benchmark.json")
    benchmark.add_argument("--online", action="store_true",
                           help="Explicitly retrieve full text via authorized NIH BioC API.")
    benchmark.add_argument("--limit", type=int, default=20)

    evaluate = sub.add_parser(
        "evaluate-labels", help="Evaluate complete, expert-adjudicated labels against frozen PMC outputs."
    )
    evaluate.add_argument("benchmark", help="Frozen PMC benchmark JSON report.")
    evaluate.add_argument("labels", help="External blinded expert-label JSON file.")
    evaluate.add_argument("--out", default="expert-validation-report.json")

    pack = sub.add_parser(
        "validation-pack",
        help="Fetch frozen PMC papers and create blinded reviewer worksheets without predictions.",
    )
    pack.add_argument("benchmark", help="Frozen PMC benchmark JSON report.")
    pack.add_argument("--reviewer", action="append", required=True,
                      help="Declared reviewer ID; repeat exactly twice.")
    pack.add_argument("--code", action="append", required=True,
                      help="Preregistered finding code; repeatable.")
    pack.add_argument("--manual", default=None,
                      help="Optional coding manual copied into the pack.")
    pack.add_argument("--out-dir", required=True,
                      help="New or empty external directory for texts and worksheets.")
    pack.add_argument("--online", action="store_true",
                      help="Explicitly retrieve full text via authorized NIH BioC API.")

    merge = sub.add_parser(
        "adjudicate-labels",
        help="Merge two blinded worksheets and third-party disagreement decisions.",
    )
    merge.add_argument("benchmark", help="Frozen PMC benchmark JSON report.")
    merge.add_argument("reviewer_a", help="First reviewer's completed worksheet.")
    merge.add_argument("reviewer_b", help="Second reviewer's completed worksheet.")
    merge.add_argument("adjudications", help="Adjudicator decisions for every disagreement.")
    merge.add_argument("--out", default="adjudicated-labels.json")

    language_benchmark = sub.add_parser(
        "benchmark-language",
        help="Quantify offline language-rule agreement with frozen human-edited science sentences.",
    )
    language_benchmark.add_argument("input", help="Human-annotated arXivEdits CSV (not bundled).")
    language_benchmark.add_argument(
        "--expected-sha256", required=True,
        help="Pin the exact bytes of the externally sourced CSV.",
    )
    language_benchmark.add_argument("--out", default="language-benchmark.json")
    language_benchmark.add_argument("--max-rows", type=int, default=2000)

    cohort = sub.add_parser(
        "domain-aggregate",
        help="Aggregate >=2 externally adjudicated, blinded domain review reports.",
    )
    cohort.add_argument("reports", nargs="+", help="JSON reports from domain-validate.")
    cohort.add_argument("--out", default="domain-cohort.json")

    science = sub.add_parser(
        "verify-science",
        help="Validate explicitly structured CI claims, SI-dimension equations, and crude risk ratios.",
    )
    science.add_argument("input", help="Bounded JSON scientific-check specification.")
    science.add_argument("--out", default="science-verification.json", help="Output JSON path.")

    args = parser.parse_args()
    if args.command == "verify-logic":
        return execute_logic_command(args, parser, _reject_input_overwrite, _same_document)
    if args.command in ("verify-toolkit",'prepare-inspection','benchmark-evidence'):
        return execute_toolkit_command(args, parser, _reject_input_overwrite, _same_document)
    if args.command in ("review", "capabilities"):
        return execute_review_command(args, parser, _reject_input_overwrite, _same_document, review_manuscript)
    if args.command == "paper-review":
        prefix = Path(args.out)
        json_path, md_path = prefix.with_suffix(".json"), prefix.with_suffix(".md")
        _reject_input_overwrite(parser, [args.input], [json_path, md_path])
        if _same_document(json_path, md_path):
            parser.error("Paper review JSON and Markdown outputs must be separate files.")
        try:
            result = review_paper(
                args.input, model=args.model, base_url=args.base_url,
                api_key_env=args.api_key_env, timeout=args.timeout,
                chunk_chars=args.chunk_chars, pdf_ocr_mode=args.ocr_mode,
                ocr_languages=args.ocr_languages, visual_pages=args.visual_pages,
            )
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
            markdown = paper_review_markdown(result)
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            parser.error(str(exc))
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(serialized, encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")
        print(f"Paper extracted text analyzed: {result['covered_characters']}/{result['extracted_characters']} characters in {result['chunks_reviewed']} chunks.")
        print("Source quotes are checked; scientific interpretations remain advisory.")
        print(f"JSON: {json_path.resolve()}")
        print(f"Markdown: {md_path.resolve()}")
        return 0

    if args.command == "benchmark-language":
        try:
            result = evaluate_arxiv_edit_pairs(
                args.input, expected_sha256=args.expected_sha256,
                max_rows=args.max_rows,
            )
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        except (OSError, ValueError, TypeError, UnicodeError, SyntaxError, RecursionError) as exc:
            parser.error(str(exc))
        out = Path(args.out)
        if _same_document(out, Path(args.input).expanduser()):
            parser.error("Output must not overwrite the annotated corpus.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        rates = result["conditional_detection"]
        print(f"Evaluated {result['rows_evaluated']} real scientific revision pairs "
              f"from {result['unique_papers']} papers.")
        print(f"Human language-edit detection recall: "
              f"{rates['positive_recall']:.2%}")
        print("Not general grammar correctness or full-manuscript scientific validation.")
        print(f"Report: {out.resolve()}")
        return 0

    if args.command == "domain-aggregate":
        try:
            result = aggregate_domain_reports(args.reports)
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            parser.error(str(exc))
        out = Path(args.out)
        if any(_same_document(out, Path(p).expanduser()) for p in args.reports):
            parser.error("Output must not overwrite an input review.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"Aggregated {result['manuscripts']} externally supplied domain reviews.")
        print("Reviewer identity/independence NOT independently verified.")
        print(f"Report: {out.resolve()}")
        return 0

    if args.command == "writing-audit":
        try:
            result = audit_academic_writing(
                args.input, genre=args.genre,
                abstract_min_words=args.abstract_min_words,
                abstract_max_words=args.abstract_max_words,
                style_language=args.style_language, design=args.design,
                discipline=args.discipline, grammar_engine=args.grammar_engine,
                grammar_port=args.grammar_port, grammar_timeout=args.grammar_timeout,
            )
            prefix = Path(args.out)
            json_path, md_path = prefix.with_suffix(".json"), prefix.with_suffix(".md")
            source = Path(args.input).expanduser().resolve()
            if _same_document(source, json_path) or _same_document(source, md_path):
                raise ValueError("Output paths must not overwrite the input manuscript.")
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
            markdown = writing_report_markdown(result)
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            parser.error(str(exc))
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(serialized, encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")
        print(f"Writing audit: {len(result['findings'])} editorial finding(s); "
              f"{len(result['style_suggestions'])} rule-based language suggestion(s); "
              f"{len(result['grammar_suggestions'])} local grammar suggestion(s).")
        if result.get("discipline_review"):
            print(f"Domain evidence items: {len(result['discipline_review']['items'])}; "
                  "all require expert oversight.")
        print(f"JSON: {json_path.resolve()}")
        print(f"Markdown: {md_path.resolve()}")
        return 0

    if args.command in ("domain-review", "domain-template", "domain-validate"):
        try:
            if args.command == "domain-review":
                result = audit_domain_file(args.input, args.discipline)
            elif args.command == "domain-template":
                result = make_domain_template(load_document(args.input), args.discipline)
            else:
                with Path(args.assessments).open("r", encoding="utf-8") as stream:
                    completed = json.load(stream)
                result = validate_domain_adjudication(
                    load_document(args.input), args.discipline, completed,
                )
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
            parser.error(str(exc))
        out = Path(args.out)
        source_paths = [Path(args.input).expanduser().resolve()]
        if args.command == "domain-validate":
            source_paths.append(Path(args.assessments).expanduser().resolve())
        if any(_same_document(out, path) for path in source_paths):
            parser.error("Output must not overwrite manuscript or assessments.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"{args.command}: {out.resolve()}")
        return 0

    if args.command == "doi-check":
        try:
            result = verify_dois(args.input, online=args.online, limit=args.limit)
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            parser.error(str(exc))
        out = Path(args.out)
        if _same_document(out, Path(args.input).expanduser()):
            parser.error("Output must not overwrite the original document.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"DOI scan: {result['found_count']} found; {result['checked_count']} returned.")
        print(f"Report: {out.resolve()}")
        return 0

    if args.command == "benchmark-pmc":
        try:
            result = run_pmc_benchmark(args.manifest, online=args.online, limit=args.limit)
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            parser.error(str(exc))
        out = Path(args.out)
        if _same_document(out, Path(args.manifest).expanduser()):
            parser.error("Output must not overwrite the input manifest.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"PMC test: {result['processed']}/{result['total_requested']} processed.")
        print("Expert-labeled scientific performance: NOT EVALUATED.")
        print(f"Report: {out.resolve()}")
        return 0 if result["failed"] == 0 else 1

    if args.command == "evaluate-labels":
        try:
            result = evaluate_blinded_labels(args.benchmark, args.labels)
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
            parser.error(str(exc))
        out = Path(args.out)
        if out.resolve() in (Path(args.benchmark).resolve(), Path(args.labels).resolve()):
            parser.error("Output must not overwrite the benchmark or label source.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"Evaluated {result['labelled_units']} blinded-labelled units.")
        print(f"Report: {out.resolve()}")
        return 0

    if args.command == "validation-pack":
        try:
            result = build_validation_pack(
                args.benchmark, args.out_dir, args.reviewer, args.code,
                online=args.online, manual_path=args.manual,
            )
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            parser.error(str(exc))
        print(f"Validation pack: {result['paper_count']} papers, {result['unit_count']} units.")
        print("Automated predictions: NOT INCLUDED; two independent reviewers must label every unit.")
        print(f"Pack: {Path(args.out_dir).resolve()}")
        return 0

    if args.command == "adjudicate-labels":
        try:
            result = merge_adjudicated_labels(
                args.benchmark, args.reviewer_a, args.reviewer_b, args.adjudications
            )
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
            parser.error(str(exc))
        out = Path(args.out)
        inputs = [args.benchmark, args.reviewer_a, args.reviewer_b, args.adjudications]
        if any(_same_document(out, Path(item)) for item in inputs):
            parser.error("Output must not overwrite the benchmark, worksheets or adjudications.")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(
            f"Merged {len(result['cases'])} units; "
            f"{result['inter_reviewer_agreement']['disagreements']} disagreement(s)."
        )
        print(f"Labels: {out.resolve()}")
        return 0

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
