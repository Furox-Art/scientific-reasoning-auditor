"""Read-only CLI for optional formal logic verification."""
import json
from pathlib import Path

from sra.document import load_document
from sra.logic import verify_logic_spec
from sra.logic_report import logic_markdown
from sra.review import load_spec_file


def configure_logic_commands(sub) -> None:
    command = sub.add_parser("verify-logic", help="Check supplied Boolean/linear formulas using optional Z3; never edit a manuscript.")
    command.add_argument("input", help="Bounded formal logic JSON specification.")
    command.add_argument("--manuscript", help="Optional source manuscript for identity and quotation checks.")
    command.add_argument("--out", default="logic-review", help="Separate JSON/Markdown report prefix.")


def execute_logic_command(args, parser, protect, same_document) -> int:
    prefix = Path(args.out)
    targets = [prefix.with_suffix(".json"), prefix.with_suffix(".md")]
    protect(parser, [args.input, args.manuscript], targets)
    if same_document(*targets):
        parser.error("Logic JSON and Markdown outputs must be separate files.")
    try:
        document = load_document(args.manuscript) if args.manuscript else None
        report = verify_logic_spec(load_spec_file(args.input), document=document)
        contents = [json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), logic_markdown(report)]
        for target, content in zip(targets, contents):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    except (OSError, ValueError, RuntimeError, TypeError, RecursionError) as exc:
        parser.error(f"Formal verification could not complete ({type(exc).__name__}); validate input and install the [logic] extra.")
    print(f"Formal verification execution: {report['execution_status']}; results concern supplied assumptions only.")
    print(f"JSON: {targets[0].resolve()}")
    print(f"Markdown: {targets[1].resolve()}")
    return 0 if report["execution_status"] == "complete" else 1
