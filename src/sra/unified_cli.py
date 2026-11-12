"""CLI adapter for unified review; execution outcomes are not scientific verdicts."""
import json
from pathlib import Path

from sra.capabilities import capabilities, STUDY_TYPES
from sra.domain_evidence import PROFILES
from sra.review import load_spec_file, review_manuscript
from sra.review_report import review_markdown


def configure_review_commands(sub) -> None:
    sub.add_parser("capabilities", help="List supported checks, profiles and assessment limits as JSON.")
    command = sub.add_parser("review", help="Compose a source-bound, cross-disciplinary review.")
    command.add_argument("input")
    command.add_argument("--out", default="review-report")
    command.add_argument("--study-type", choices=STUDY_TYPES, default="unknown")
    command.add_argument("--discipline", action="append", choices=tuple(PROFILES), default=[])
    command.add_argument("--style-language", choices=("en", "tr", "none"), default="en")
    command.add_argument("--statistics-spec", help="Explicit bounded statistics JSON; never inferred from prose.")
    command.add_argument("--scientific-spec", help="Explicit bounded scientific-check JSON.")
    command.add_argument("--logic-spec", help="Source-bound Boolean/linear formulas for optional Z3 verification.")
    command.add_argument("--toolkit-spec", help="Source-bound local mathematics, units, data replay and candidate checks.")
    command.add_argument("--online", action="store_true", help="Send DOI identifiers to registries; not claim verification.")
    command.add_argument("--send-to-model", action="store_true", help="Explicitly transmit the extracted manuscript to the configured model.")
    command.add_argument("--model")
    command.add_argument("--base-url", default="https://api.openai.com/v1")
    command.add_argument("--api-key-env", default="OPENAI_API_KEY")
    command.add_argument("--timeout", type=int, default=120)
    command.add_argument("--chunk-chars", type=int, default=12000)
    command.add_argument("--ocr-mode", choices=("off", "missing", "all"), default="off")
    command.add_argument("--ocr-languages", default="eng")
    command.add_argument("--visual-pages", action="store_true", help="Explicitly send all PDF page images; requires model consent.")


def execute_review_command(args, parser, protect, same_document, review=review_manuscript) -> int:
    if args.command == "capabilities":
        print(json.dumps(capabilities(), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    prefix = Path(args.out)
    targets = [prefix.with_suffix(".json"), prefix.with_suffix(".md")]
    protect(parser, [args.input, args.statistics_spec, args.scientific_spec, args.logic_spec, args.toolkit_spec], targets)
    if same_document(*targets):
        parser.error("Review JSON and Markdown outputs must be separate files.")
    try:
        result = review(
            args.input, study_type=args.study_type, disciplines=args.discipline,
            style_language=args.style_language, online=args.online,
            statistics_spec=load_spec_file(args.statistics_spec) if args.statistics_spec else None,
            scientific_spec=load_spec_file(args.scientific_spec) if args.scientific_spec else None,
            logic_spec=load_spec_file(args.logic_spec) if args.logic_spec else None,
            toolkit_spec=load_spec_file(args.toolkit_spec) if args.toolkit_spec else None,
            send_to_model=args.send_to_model, model=args.model, base_url=args.base_url,
            api_key_env=args.api_key_env, timeout=args.timeout, chunk_chars=args.chunk_chars,
            pdf_ocr_mode=args.ocr_mode, ocr_languages=args.ocr_languages, visual_pages=args.visual_pages,
        )
        serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        markdown = review_markdown(result)
        for target, content in zip(targets, (serialized, markdown)):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    except (OSError, ValueError, RuntimeError, TypeError, RecursionError) as exc:
        parser.error(f"Unified review could not complete ({type(exc).__name__}); check inputs and configuration.")
    print(f"Execution: {result['execution_status']}; not scientific quality or validity.")
    print(f"JSON: {targets[0].resolve()}")
    print(f"Markdown: {targets[1].resolve()}")
    return 0 if result["execution_status"] == "complete" else 1
