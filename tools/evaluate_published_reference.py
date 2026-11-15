"""Offline, pinned SRA 0.9.0 comparison with a historical manual reference.

Source strings were supplied by statcheck, not extracted by SRA. No whole-paper
accuracy, new human reviews, authenticated labels or held-out validity is claimed.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import sra
from sra.error_benchmark import decision, fingerprint
from sra.error_evaluation import _summary
from sra.toolkit import verify_toolkit_spec, _numerical_environment
from sra.toolkit_spec import prepare_toolkit_spec

WORKBOOK_NAME = '150702ComparePvaluesPLOSStatcheckOrderedCleaned.xlsx'
WORKBOOK_SHA = '74a91b05cd738a2cccccfe7ec6dfb8aa5ed46b248b3d1a7d76bd67513bdf6f80'
CODEBOOK_NAME = '150706CodeBookComparisonStatcheckPLOS.docx'
CODEBOOK_SHA = 'b2d88b9bc4edf06e4d9228ba358b4e295f5e4f2824d26c6c7720e32e4d7f0c36'
WHEEL_NAME = 'scientific_reasoning_auditor-0.9.0-py3-none-any.whl'
WHEEL_SHA = '9aaab314b17f4ae311f842f89409f29430451312df493ba1c59510df21cb9e93'
PROTOCOL = Path(__file__).resolve().parents[1] / 'benchmarks/pilots/published-reference-20261116/protocol.md'
CLARIFICATION = PROTOCOL.with_name('parser-clarification.md')
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
NUMBER = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
EXPRESSION = re.compile(
    r'(?P<test>t|F|Chi2|χ2|χ²|X2)\s*\((?P<df>[^()]*)\)\s*'
    r'(?P<stat_op><=|>=|[=<>≤≥])\s*(?P<stat>'+NUMBER+r')\s*[,;]\s*'
    r'p\s*(?P<p_op><=|>=|[=<>≤≥])\s*(?P<p>'+NUMBER+r')\s*\.?', re.I)


def pinned_bytes(path, expected, maximum):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum+1)
    if len(raw) > maximum or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Source size/hash differs from the frozen reference.')
    return raw


def _archive(raw):
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = z.namelist()
        if len(names) != len(set(names)) or len(names) > 1000 or sum(x.file_size for x in z.infolist()) > 8*1024*1024:
            raise ValueError('Archive membership or expanded size is outside its bound.')
        return z
    except zipfile.BadZipFile as exc:
        raise ValueError('A valid bounded ZIP archive is required.') from exc


def _xml(z, name):
    raw = z.read(name)
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('XML entity/document-type declarations are unsupported.')
    return ET.fromstring(raw)


def read_workbook(raw):
    """Read literal inputs/cached historical labels; never recalculate formulas."""
    if len(raw) > 2*1024*1024:
        raise ValueError('Reference workbook exceeds 2 MiB.')
    try:
        with _archive(raw) as z:
            sheets = _xml(z, 'xl/workbook.xml').findall('s:sheets/s:sheet', NS)
            if len(sheets) != 1 or sheets[0].get('name') != 'p1148checked':
                raise ValueError('Expected the single published reference worksheet.')
            strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                strings = [''.join(t.text or '' for t in si.findall('.//s:t', NS))
                           for si in _xml(z, 'xl/sharedStrings.xml').findall('s:si', NS)]
            data, seen, projected = [], set(), None
            for row in _xml(z, 'xl/worksheets/sheet1.xml').findall('s:sheetData/s:row', NS):
                n = int(row.get('r', '0'))
                if not 1 <= n <= 20000 or n in seen:
                    raise ValueError('Worksheet row identities are invalid.')
                seen.add(n)
                cells = {}
                for cell in row.findall('s:c', NS):
                    address = re.fullmatch(r'([A-Z]{1,3})([0-9]+)', cell.get('r', ''))
                    if not address or int(address[2]) != n or address[1] in cells:
                        raise ValueError('Duplicate/malformed cells are unsupported.')
                    column = address[1]
                    if projected is not None and column not in projected:
                        cells[column] = ''
                        continue
                    if cell.find('s:f', NS) is not None and (projected is None or projected[column] != 'plosErrorLogical'):
                        raise ValueError('Prediction inputs and manual source labels must be literal.')
                    value = cell.find('s:v', NS)
                    value = '' if value is None else value.text or ''
                    kind = cell.get('t')
                    if kind == 's':
                        index = int(value)
                        if not 0 <= index < len(strings):
                            raise ValueError('Shared-string index is invalid.')
                        value = strings[index]
                    elif kind == 'inlineStr':
                        value = ''.join(t.text or '' for t in cell.findall('.//s:t', NS))
                    elif kind not in (None, 'n', 'b'):
                        raise ValueError('Unsupported reference cell type.')
                    if len(value) > 10000:
                        raise ValueError('Reference cell exceeds its text bound.')
                    cells[address[1]] = value
                if n == 1:
                    selected = {'authors','statRaw','plosError','plosErrorLogical','plosStatistic'}
                    projected = {key:value for key,value in cells.items() if value in selected}
                data.append((n, cells))
    except (KeyError, ET.ParseError, TypeError, OverflowError) as exc:
        raise ValueError('Malformed published reference workbook.') from exc
    if not data or data[0][0] != 1:
        raise ValueError('Reference headers are absent.')
    headers = {key: value for key, value in data[0][1].items() if value}
    if len(set(headers.values())) != len(headers) or not {'authors','statRaw','plosError','plosErrorLogical'} <= set(headers.values()):
        raise ValueError('Reference headers are missing or duplicated.')
    headers = {key:name for key,name in headers.items() if name in ('authors','statRaw','plosError','plosErrorLogical','plosStatistic')}
    result = []
    for n, cells in data[1:]:
        if any(value and key not in headers for key, value in cells.items()):
            raise ValueError('Nonempty data has no corresponding header.')
        result.append({'source_row': n, **{name: cells.get(key, '') for key, name in headers.items()}})
    return result


def parse_expression(raw, ident):
    """Only this input string can influence the structured check."""
    if not isinstance(raw, str) or len(raw) > 2000:
        return None, 'invalid_raw_expression'
    text = ' '.join(raw.replace('−', '-').split())
    if text in ('', 'NA'):
        return None, 'raw_expression_missing'
    match = EXPRESSION.fullmatch(text)
    if not match:
        return None, 'unsupported_literal_expression'
    if match['stat_op'] != '=':
        return None, 'inexact_test_statistic'
    if match['p_op'] not in ('=', '<', '>'):
        return None, 'unsupported_p_relation'
    dfs = [v.strip() for v in match['df'].split(',')]
    if not all(re.fullmatch(r'[0-9]{1,7}', value) for value in dfs):
        return None, 'unsupported_degrees_of_freedom'
    test = match['test'].lower()
    test = 't' if test == 't' else 'F' if test == 'f' else 'chi2'
    check = dict(id=ident, kind='statistic_consistency', test=test,
                 statistic=match['stat'], df=[int(v) for v in dfs],
                 reported_p=match['p'], relation=match['p_op'])
    try:
        prepare_toolkit_spec(dict(schema_version='1.0', checks=[check]))
    except ValueError:
        return None, 'unsupported_check_input'
    return check, None


def _reference_summary(rows):
    result = _summary(rows)
    result['metrics']['reference_frame_recall'] = result['metrics'].pop('end_to_end_recall')
    return result


def compare_rows(rows):
    cases, checks = [], []
    exclusions = dict(no_manual_reference=0, source_study_exclusion=0)
    for row in rows:
        human, complement = row.get('plosErrorLogical', ''), row.get('plosError', '')
        missing = ('', 'NA')
        if human in missing and complement in missing:
            gold, excluded = None, 'no_manual_reference'
        else:
            if human not in ('0','1') or complement not in ('0','1') or int(human)+int(complement) != 1 or not row.get('authors','').strip():
                raise ValueError('Manual reference labels/author keys are missing or inconsistent.')
            gold = 'error' if human == '1' else 'no_error'
            excluded = 'source_study_exclusion' if 'Stapel' in row['authors'] else None
        ident = 'row_'+str(row['source_row'])
        raw = row.get('statRaw', '')
        case = dict(id=ident, source_row=row['source_row'],
                    group_id='paper_'+hashlib.sha256(row.get('authors','').encode()).hexdigest()[:16],
                    gold=gold, source_test=row.get('plosStatistic','unspecified'), raw_expression=raw,
                    input_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                    prediction='abstain', exclusion=excluded, abstention_reason=None, check_result=None)
        if excluded:
            exclusions[excluded] += 1
        else:
            check, reason = parse_expression(raw, ident)
            case['abstention_reason'] = reason
            if check:
                checks.append(check)
        cases.append(case)
    if len({case['id'] for case in cases}) != len(cases):
        raise ValueError('Source row identities must be unique.')
    by_id = {case['id']: case for case in cases}
    partial = False
    for start in range(0, len(checks), 32):
        batch = checks[start:start+32]
        report = verify_toolkit_spec(dict(schema_version='1.0', checks=batch))
        results = report['checks']
        if len(results) != len(batch) or {r.get('id') for r in results} != {r['id'] for r in batch}:
            raise ValueError('Engine results do not cover each requested check exactly once.')
        for result in results:
            if result.get('kind') != 'statistic_consistency' or result.get('status') not in ('VERIFIED','REFUTED','UNDETERMINED','UNAVAILABLE','FAILED'):
                raise ValueError('Unsupported engine result contract.')
            case = by_id[result['id']]
            case['check_result'] = result
            case['prediction'] = decision(result['kind'], result['status'])
            if case['prediction'] == 'abstain':
                case['abstention_reason'] = 'engine_'+result['status'].lower()
            partial |= result['status'] in ('FAILED','UNAVAILABLE')
    eligible = [case for case in cases if case['exclusion'] is None]
    groups = sorted({case['group_id'] for case in eligible})
    return dict(execution_status='partial' if partial else 'complete',
        total_rows=len(cases), exclusions=exclusions, group_count=len(groups),
        summary=_reference_summary(eligible), cases=cases,
        abstention_reasons=dict(sorted(Counter(case['abstention_reason'] for case in eligible if case['prediction']=='abstain').items())),
        by_group={group:_reference_summary([c for c in eligible if c['group_id']==group]) for group in groups},
        group_omissions=[dict(omitted_group=group, summary=_reference_summary([c for c in eligible if c['group_id']!=group]))
                         for group in groups] if len(groups) >= 2 else [])


def verify_engine(path):
    raw = pinned_bytes(path, WHEEL_SHA, 2*1024*1024)
    if sra.__version__ != '0.9.0':
        raise ValueError('This comparison requires the unchanged released SRA 0.9.0.')
    package = Path(sra.__file__).resolve().parent
    with _archive(raw) as z:
        names = {n for n in z.namelist() if n.startswith('sra/') and (n.endswith('.py') or n.endswith('/py.typed'))}
        local = {'sra/'+p.relative_to(package).as_posix(): p for p in package.rglob('*')
                 if p.is_file() and (p.suffix=='.py' or p.name=='py.typed')}
        if set(local) != names or any(p.read_bytes() != z.read(name) for name,p in local.items()):
            raise ValueError('Installed engine source differs from the pinned released wheel.')
    return dict(version='0.9.0', wheel_sha256=WHEEL_SHA, source_files_verified=len(local),
                numerical_environment=_numerical_environment())


def run_reference(workbook, codebook, engine_wheel):
    raw = pinned_bytes(workbook, WORKBOOK_SHA, 2*1024*1024)
    pinned_bytes(codebook, CODEBOOK_SHA, 128*1024)
    engine = verify_engine(engine_wheel)
    rows = read_workbook(raw)
    report = compare_rows(rows)
    if (report['total_rows'], report['summary']['binary_labeled_cases'], report['group_count'],
            report['exclusions']) != (1211,1120,48,dict(no_manual_reference=63,source_study_exclusion=28)):
        raise ValueError('Reference cohort accounting differs from the frozen specification.')
    report.update(schema_version='published-statistics-comparison/1.0',
        comparison_mode='retrospective_reference_agreement', engine=engine,
        workbook_sha256=WORKBOOK_SHA, codebook_sha256=CODEBOOK_SHA,
        specification_sha256=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        parser_clarification_sha256=hashlib.sha256(CLARIFICATION.read_bytes()).hexdigest(),
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reference_label_origin='historical_manual_coding_as_described_by_source',
        new_human_reviews_collected=0, reference_identity_verified=False,
        sra_text_extraction_evaluated=False, full_papers_read=False, uncertainty_intervals=None,
        source_attribution='Wicherts, Bakker & Molenaar (2011); comparison/codebook curated for Nuijten et al. statcheck validation (2016/2017).',
        source_license='CC BY 4.0, as declared by https://osf.io/yu5wj/; https://creativecommons.org/licenses/by/4.0/',
        source_urls=['https://osf.io/axfbn/','https://osf.io/xqce2/','https://osf.io/zcysv/'],
        limitations=['Selected significant psychology results; no representative multi-field or held-out validation.',
            'Inputs are third-party-extracted strings, not SRA paper extraction. Missing strings abstain.',
            'Predictions use only statRaw; manually adjusted numbers, comments and other software labels are not inputs.',
            'The unchanged 0.9.0 method assumes two-sided t or upper-tail F/chi-square with exact integer df.',
            'Historical labels/joins and original papers are not independently re-adjudicated or authenticated.',
            'Contextual corrections or one-tailed tests may explain disagreement; no whole-paper truth or author misconduct verdict follows.',
            'Case counts are correlated within source author-key groups. Omission sensitivity is not a confidence interval.',
            'Source byte checks support reproducibility, not independent scientific expert validation.'])
    report['report_sha256'] = fingerprint(report)
    return report


def markdown(report):
    lines = ['# Published statistical-reference comparison', '',
        'Retrospective, conditional reference agreement. Not whole-paper scientific accuracy.', '',
        'Execution: '+report['execution_status'],
        'Workbook rows: '+str(report['total_rows']),
        'Manually labeled retained rows: '+str(report['summary']['binary_labeled_cases']),
        'Source author-key groups: '+str(report['group_count']),
        'Exclusions: '+json.dumps(report['exclusions'], sort_keys=True), '',
        'Confusion: '+json.dumps(report['summary']['confusion'], sort_keys=True),
        'Abstentions: '+json.dumps(report['summary']['abstentions'], sort_keys=True), '',
        '| Metric | Numerator | Denominator | Value |','| --- | --- | --- | --- |']
    for key, metric in report['summary']['metrics'].items():
        value = 'undefined' if metric['value'] is None else f"{metric['value']:.6g}"
        title = 'reference_frame_recall' if key=='end_to_end_recall' else key
        lines.append(f"| {title} | {metric['numerator']} | {metric['denominator']} | {value} |")
    lines += ['', '## Abstention reasons', '', *('- '+key+': '+str(n) for key,n in report['abstention_reasons'].items()),
              '', '## Source and reproducibility', '', report['source_attribution'], '', report['source_license'], '',
              *('- '+url for url in report['source_urls']), '',
              'Engine: '+report['engine']['version']+'; wheel SHA-256: '+report['engine']['wheel_sha256'],
              'Specification SHA-256: '+report['specification_sha256'],
              'Parser clarification SHA-256: '+report['parser_clarification_sha256'],
              'Producer SHA-256: '+report['producer_sha256'],
              'Report SHA-256: '+report['report_sha256'], '',
              '## Limits', '', *('- '+value for value in report['limitations']), '',
              'Complete case results, group strata and whole-group omissions are retained in the companion JSON.']
    return '\n'.join(lines)+'\n'


def write_reports(prefix, report, text):
    paths = [Path(prefix).with_suffix(suffix) for suffix in ('.json','.md')]
    if any(p.exists() or p.is_symlink() for p in paths):
        raise FileExistsError('Outputs already exist; choose a new report prefix.')
    payloads = [json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), text]
    if len(payloads[0].encode()) > 4*1024*1024:
        raise ValueError('Complete report exceeds 4 MiB; no truncated report written.')
    for path, payload in zip(paths,payloads):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(payload)


def download_sources(folder):
    folder = Path(folder)
    sources = [(WORKBOOK_NAME,'https://osf.io/download/axfbn/',WORKBOOK_SHA,2*1024*1024),
               (CODEBOOK_NAME,'https://osf.io/download/xqce2/',CODEBOOK_SHA,128*1024)]
    with urllib.request.urlopen('https://pypi.org/pypi/scientific-reasoning-auditor/0.9.0/json',timeout=30) as response:
        metadata = json.loads(response.read(1024*1024))
    selected = [x for x in metadata['urls'] if x['filename']==WHEEL_NAME and x['digests']['sha256']==WHEEL_SHA]
    if len(selected) != 1 or not selected[0]['url'].startswith('https://files.pythonhosted.org/'):
        raise ValueError('Pinned public wheel metadata differs.')
    sources.append((WHEEL_NAME,selected[0]['url'],WHEEL_SHA,2*1024*1024))
    if any((folder/name).exists() or (folder/name).is_symlink() for name,_,_,_ in sources):
        raise FileExistsError('Source outputs already exist; choose a new directory.')
    folder.mkdir(parents=True,exist_ok=True)
    for name,url,expected,bound in sources:
        with urllib.request.urlopen(url,timeout=30) as response:
            raw = response.read(bound+1)
        if len(raw)>bound or hashlib.sha256(raw).hexdigest()!=expected:
            raise ValueError('Downloaded source bytes differ from the pinned reference.')
        with (folder/name).open('xb') as stream:
            stream.write(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    download = commands.add_parser('download',help='Explicit public network retrieval of three pinned inputs.')
    download.add_argument('--out-dir',type=Path,required=True)
    run = commands.add_parser('run',help='Offline comparison; source files remain unchanged.')
    for name in ('workbook','codebook','engine-wheel','out'):
        run.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args(argv)
    if args.command=='download':
        download_sources(args.out_dir)
        print('Downloaded pinned public inputs; no evaluation or human decisions generated.')
        return 0
    report = run_reference(args.workbook,args.codebook,args.engine_wheel)
    write_reports(args.out,report,markdown(report))
    print('Reference comparison: '+report['execution_status']+'; no whole-paper accuracy claim.')
    return 0 if report['execution_status']=='complete' else 1


if __name__=='__main__':
    raise SystemExit(main())
