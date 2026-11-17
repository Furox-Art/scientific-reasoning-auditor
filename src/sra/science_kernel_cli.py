"""Separate reports for the standalone scientific proof kernel."""
import json
from pathlib import Path

from sra.science_kernel_spec import MAX_BYTES
from sra.report import _safe_md

COMMANDS = ('prove-science', 'verify-science-certificate')


def _display(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def science_proof_markdown(report):
    if report['schema_version'] == 'scientific-proof-verification/1.0':
        return '# Scientific proof certificate verification\n\n' + f"Valid: {report['valid']}\n\n{_safe_md(report['scope'])}\n"
    lines = ['# Scientific proof kernel', '', 'These are formal conclusions under supplied premises and interval bounds.',
             'They are not certifications of scientific truth.', '',
             f"- Kernel: {_safe_md(report['engine_version'])}", f"- Input SHA-256: {report['input_sha256']}",
             f"- Certificate SHA-256: {report['certificate_sha256']}",
             f"- Premises: {report['basis_state']}",
             f"- Admissible worlds: {report['admissible_worlds']} of {report['universe_worlds']}", '', '## Conclusions', '']
    for claim in report['claims']:
        lines.extend([f"### {_safe_md(claim['id'])}: {claim['status']}",
                      f"- Statement: {_safe_md(_display(claim['expression']))}",
                      f"- Scope: {_safe_md(claim['scope'])}", f"- Reason: {_safe_md(claim['reason'])}",
                      '- Basis: ' + (', '.join(_safe_md(key) for key in claim['basis_ids']) or 'no asserted basis'),
                      '- Supporting world: ' + _safe_md(_display(claim['supporting_world'])),
                      '- Counter-world: ' + _safe_md(_display(claim['counter_world'])), ''])
    lines.extend(['## Premises and source evidence', ''])
    for row in report['premises']:
        value = 'unknown' if row['value'] is None else 'true' if row['value'] else 'false'
        lines.append(f"- **{_safe_md(row['id'])}:** {_safe_md(row['atom'])} = {value} ({row['origin']})")
        for ref in row['source_refs']:
            lines.append(f"> {_safe_md(ref['source_id'])} [{ref['start']}, {ref['end']}): {_safe_md(ref['quote'])}")
    lines.extend(['', '## Rule assumptions', ''])
    lines.extend('- ' + _safe_md(_display(row)) for row in report['rules'])
    lines.extend(['', '## Source snapshots', ''])
    lines.extend('- ' + _safe_md(_display(row)) for row in report['sources'])
    lines.extend(['', '## Native exact arithmetic', ''])
    lines.extend('- ' + _safe_md(_display(row)) for row in report['arithmetic'])
    lines.extend(['', '## Conflict core', '', _safe_md(_display(report['conflict_core'])), '', '## Limits', ''])
    lines.extend('- ' + _safe_md(limit) for limit in report['limitations'])
    return '\n'.join(lines) + '\n'


def configure_science_commands(sub):
    for name in COMMANDS:
        command = sub.add_parser(name, help='Run the independent finite scientific proof kernel or recheck its certificate.')
        command.add_argument('spec')
        if name == COMMANDS[1]:
            command.add_argument('certificate')
        command.add_argument('--out', default='science-proof' if name == COMMANDS[0] else 'science-proof-verification')


def _read(path):
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Proof files require 1 byte to 1 MiB.')
    return data.decode('utf-8-sig')


def execute_science_command(args, parser, protect, same_document):
    from sra.science_kernel import prove_science
    from sra.science_certificate import verify_science_certificate
    targets = [Path(args.out).with_suffix('.json'), Path(args.out).with_suffix('.md')]
    protect(parser, [args.spec, getattr(args, 'certificate', None)], targets)
    if same_document(*targets):
        parser.error('Proof JSON and Markdown output files must be separate.')
    try:
        spec = _read(args.spec)
        report = prove_science(spec) if args.command == COMMANDS[0] else verify_science_certificate(spec, _read(args.certificate))
        for target, content in zip(targets, (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), science_proof_markdown(report))):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8', newline='\n')
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        parser.error(f'Scientific proof could not complete ({type(exc).__name__}); check bounded structured input.')
    print('Finite formal engine completed; empirical scientific truth is not certified.')
    return 1 if report.get('valid') is False else 0
