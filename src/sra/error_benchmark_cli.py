"""Separate reports for frozen structured-error cohorts; no source writes."""
import json
from pathlib import Path

from sra.error_benchmark import bounded_json, error_label_template, run_error_benchmark
from sra.error_evaluation import evaluate_errors, error_benchmark_markdown

COMMANDS = ('benchmark-errors', 'error-label-template', 'evaluate-errors')


def configure_error_commands(sub):
    for name in COMMANDS:
        command = sub.add_parser(name, help='Frozen structured-check evaluation; no scientific certification.')
        command.add_argument('input', help='Frozen benchmark manifest JSON.')
        if name == 'evaluate-errors':
            command.add_argument('predictions', help='Frozen run JSON.')
            command.add_argument('labels', help='Separately obtained labels JSON.')
        command.add_argument('--out', default='error-labels.json' if name == 'error-label-template' else 'error-benchmark')


def _read(path, maximum):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum+1)
    if len(raw) > maximum:
        raise ValueError('Benchmark input file exceeds its byte bound.')
    return bounded_json(raw.decode('utf-8'), maximum)


def execute_error_command(args, parser, protect, same_document):
    prefix = Path(args.out)
    template = args.command == 'error-label-template'
    targets = [prefix] if template else [prefix.with_suffix('.json'), prefix.with_suffix('.md')]
    protect(parser, [args.input, getattr(args, 'predictions', None), getattr(args, 'labels', None)], targets)
    if not template and same_document(*targets):
        parser.error('Benchmark JSON and Markdown outputs must be separate files.')
    try:
        manifest = _read(args.input, 1024*1024)
        if template:
            report = error_label_template(manifest)
        elif args.command == 'benchmark-errors':
            report = run_error_benchmark(manifest)
        else:
            report = evaluate_errors(manifest, _read(args.predictions, 4*1024*1024), _read(args.labels, 1024*1024))
        contents = [json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)]
        if not template:
            contents.append(error_benchmark_markdown(report))
        for target, content in zip(targets, contents):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
    except (OSError, ValueError, TypeError, RuntimeError, RecursionError) as exc:
        parser.error(f'Error benchmark could not complete ({type(exc).__name__}); check frozen inputs and optional backends.')
    print('Benchmark outputs written; no scientific certification.')
    return 0 if template or report['execution_status'] == 'complete' else 1
