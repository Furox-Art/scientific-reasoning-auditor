"""Offline distribution-table controls; never a whole-paper accuracy score."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import sra
from sra.error_benchmark import fingerprint
from sra.toolkit import verify_toolkit_spec, _numerical_environment

FOLDER=Path(__file__).resolve().parents[1]/'benchmarks/pilots/statistical-context-20261116'
CASES=FOLDER/'cases.json'
PROTOCOL=FOLDER/'protocol.md'
CLARIFICATION=FOLDER/'precision-clarification.md'
CASES_SHA='8f33fe6b94df7cd1b57b82bc1655a5d88ae844b705711050d25b8d2da74907e6'
PROTOCOL_SHA='3a6d7bff9091872c162ff010a15a070782ad547af35e5fd1c1b509b27dd77096'
CLARIFICATION_SHA='2b7af9f801caf92bf9831e3894f6e17f8a9df0b97ecf49d50b8df3c2da486068'


def pinned(path,expected):
    with Path(path).open('rb') as stream:raw=stream.read(128*1024+1)
    if len(raw)>128*1024 or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('Frozen numerical reference bytes changed; use a new protocol version.')
    return raw


def compare():
    packet=json.loads(pinned(CASES,CASES_SHA))
    pinned(PROTOCOL,PROTOCOL_SHA)
    pinned(CLARIFICATION,CLARIFICATION_SHA)
    cases=packet['cases']
    if len(cases)!=32 or len({row['check']['id'] for row in cases})!=32:
        raise ValueError('Expected all 32 distinct frozen numerical controls.')
    # Only check inputs enter the engine; expected outcomes/origins are external.
    result=verify_toolkit_spec({'schema_version':'1.0','checks':[row['check'] for row in cases]})
    if [row['id'] for row in result['checks']]!=[row['check']['id'] for row in cases]:
        raise ValueError('Engine result identities differ; no dropped/truncated case report.')
    rows=[dict(origin=expected['origin'],expected_status=expected['expected_status'],
               expectation_met=actual['status']==expected['expected_status'],result=actual)
          for expected,actual in zip(cases,result['checks'])]
    package=Path(sra.__file__).resolve().parent
    sources={'sra/'+p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(package.rglob('*')) if p.is_file() and (p.suffix=='.py' or p.name=='py.typed')}
    report=dict(schema_version='1.0',scope=packet['scope'],
        comparison_status='MATCHED' if all(row['expectation_met'] for row in rows) else 'MISMATCHED',
        case_count=len(rows),expectations_met=sum(row['expectation_met'] for row in rows),
        actual_status_counts=dict(sorted(Counter(row['result']['status'] for row in rows).items())),
        engine_execution_status=result['execution_status'],cases=rows,
        new_human_reviews_collected=0,papers_evaluated=0,source_urls=packet['sources'],
        cases_sha256=CASES_SHA,protocol_sha256=PROTOCOL_SHA,precision_clarification_sha256=CLARIFICATION_SHA,
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        engine_version=sra.__version__,numerical_environment=_numerical_environment(),
        runtime_source_sha256=fingerprint(sources),runtime_source_files=sources,
        limits=['24 NIST-derived numerical cases and 8 separately marked synthetic controls.',
                'Source selection was frozen before implementation; these are software controls, not a held-out paper cohort.',
                'Expected abstentions are retained. Matched controls do not estimate scientific precision/recall.',
                'Integer-df NIST tables do not validate all fractional-df calculations; independent analytic unit controls are separate.',
                'Tail, exact df and correction suitability remain caller declarations.',
                'Df not exactly representable by the float backend abstain; backend probability error bounds are not formally proven.',
                'No new human labels, full-paper assessment or independent expert validation.',
                'The published 0.9.0 historical first result is unchanged and not rescored.'])
    report['report_sha256']=fingerprint(report)
    return report


def markdown(report):
    lines=['# Statistical-context numerical controls','',report['scope'],'',
           'Comparison: '+report['comparison_status'],
           f"Expectations met: {report['expectations_met']} / {report['case_count']}",
           'Actual statuses: '+json.dumps(report['actual_status_counts'],sort_keys=True),'',
           '## Complete cases','',
           '| Case | Origin | Expected | Actual |','| --- | --- | --- | --- |']
    for row in report['cases']:
        lines.append('| '+ ' | '.join((row['result']['id'],row['origin'],row['expected_status'],row['result']['status']))+' |')
    lines+=['','## Reproducibility','',
            'Engine: '+report['engine_version'],
            'Fixture SHA-256: '+report['cases_sha256'],
            'Protocol SHA-256: '+report['protocol_sha256'],
            'Precision clarification SHA-256: '+report['precision_clarification_sha256'],
            'Producer SHA-256: '+report['producer_sha256'],
            'Runtime source SHA-256: '+report['runtime_source_sha256'],
            'Report SHA-256: '+report['report_sha256'],'',
            *('- '+url for url in report['source_urls']),'','## Limits','',
            *('- '+limit for limit in report['limits'])]
    return '\n'.join(lines)+'\n'


def write_reports(prefix,report):
    paths=[Path(prefix).with_suffix(suffix) for suffix in ('.json','.md')]
    if any(p.exists() or p.is_symlink() for p in paths):
        raise FileExistsError('Choose a fresh output prefix; existing reports are preserved.')
    payloads=[json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),markdown(report)]
    for path,payload in zip(paths,payloads):
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf-8',newline='\n') as stream:stream.write(payload)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    report=compare();write_reports(args.out,report)
    print(f"Numerical controls: {report['expectations_met']}/{report['case_count']} expectations met; no paper-accuracy claim.")
    return 0 if report['comparison_status']=='MATCHED' else 1


if __name__=='__main__':raise SystemExit(main())
