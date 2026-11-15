"""Read-only standalone toolkit entry point."""
import json
from pathlib import Path
from sra.document import load_document
from sra.review import load_spec_file
from sra.toolkit import verify_toolkit_spec
from sra.toolkit_report import toolkit_markdown


def configure_toolkit_commands(sub):
    prepare=sub.add_parser('prepare-inspection',help='Prepare source-located inspection candidates; execute no inferred checks.')
    prepare.add_argument('input')
    prepare.add_argument('--out',default='inspection-inputs')
    benchmark=sub.add_parser('benchmark-evidence',help='Evaluate sentence retrieval on supplied frozen SciFact corpus and claims.')
    benchmark.add_argument('input',help='Local corpus.jsonl file.')
    benchmark.add_argument('--claims',required=True,help='Local human-labelled claims JSONL split.')
    benchmark.add_argument('--out',default='evidence-benchmark')
    command = sub.add_parser("verify-toolkit",help="Run bounded local mathematics, units, data replay and candidate retrieval checks.")
    command.add_argument("input",help="Toolkit JSON specification.")
    command.add_argument("--manuscript",help="Optional read-only manuscript with matching specification hashes.")
    command.add_argument("--out",default="toolkit-review",help="Separate JSON/Markdown report prefix.")


def execute_toolkit_command(args,parser,protect,same_document):
    prefix = Path(args.out)
    targets = [prefix.with_suffix(".json"),prefix.with_suffix(".md")]
    protect(parser,[args.input,getattr(args,'manuscript',None),getattr(args,'claims',None)],targets)
    if same_document(*targets):
        parser.error("Toolkit JSON and Markdown outputs must be separate files.")
    try:
        if args.command=='benchmark-evidence':
            from sra.evidence_benchmark import evaluate_scifact,benchmark_markdown
            report=evaluate_scifact(args.input,args.claims)
            markdown=benchmark_markdown(report)
        elif args.command=='prepare-inspection':
            from sra.inspection import prepare_inspection,inspection_markdown
            report=prepare_inspection(load_document(args.input))
            markdown=inspection_markdown(report)
        else:
            document = load_document(args.manuscript) if args.manuscript else None
            report = verify_toolkit_spec(load_spec_file(args.input),document)
            markdown=toolkit_markdown(report)
        contents = [json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),markdown]
        for target,content in zip(targets,contents):
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(content,encoding="utf-8")
    except (ImportError,OSError,ValueError,RuntimeError,TypeError,RecursionError) as exc:
        parser.error(f"Toolkit input could not be processed ({type(exc).__name__}); check the specification and [toolkit] extra.")
    print(f"Toolkit execution: {report['execution_status']}; scientific validity is not established.")
    print(f"JSON: {targets[0].resolve()}")
    print(f"Markdown: {targets[1].resolve()}")
    return 0 if report["execution_status"] == "complete" else 1
