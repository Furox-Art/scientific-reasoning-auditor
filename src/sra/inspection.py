"""Prepare source-located candidates without executing inferred checks."""
import ast
import re
from bisect import bisect_right

from sra.document import without_fenced_code
from sra.toolkit_spec import digest

_NUM=r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?'
_REPORTED=re.compile(r'\b(t|F|z|chi2)\s*(?:\((\d+(?:\s*,\s*\d+)?)\))?\s*=\s*('+_NUM+r')\s*[,;]\s*p\s*([=<>])\s*('+_NUM+r')')


def prepare_inspection(document):
    text=document.text
    if len(text)>200000:
        raise ValueError('Automatic preparation is limited to 200000 extracted characters.')
    clean=without_fenced_code(text)
    # Keep original offsets: ignore code using a line mask rather than its shortened text.
    original_lines=text.splitlines(keepends=True)
    clean_lines=clean.splitlines(keepends=True)
    active=[bool(line.strip()) for line in clean_lines]
    starts=[0]
    for line in original_lines:
        starts.append(starts[-1]+len(line))
    candidates=[]
    def add(kind,start,end,**extra):
        if len(candidates)>=500:
            raise ValueError('More than 500 inspection candidates; split the source explicitly.')
        candidates.append({'id':f'candidate_{len(candidates)+1}','kind':kind,'start':start,'end':end,
            'line':bisect_right(starts,start),'source_quote':text[start:end],
            'requires_confirmation':True,**extra})
    table_start=None
    for index,line in enumerate(original_lines):
        start=starts[index]
        enabled=index<len(active) and active[index]
        table=enabled and line.lstrip().startswith('|')
        if table and table_start is None:
            table_start=start
        if table_start is not None and (not table or index==len(original_lines)-1):
            add('table',table_start,start+len(line) if table else start)
            table_start=None
        if not enabled:
            continue
        if re.search(r'\b(?:assume|assuming|assumption|provided that)\b',line,re.I):
            add('assumption',start,start+len(line.rstrip('\r\n')))
        if re.search(r'\b(?:t|F|r|z|chi2)\s*(?:\([^\n]{0,30}\))?\s*=\s*[+-]?(?:\d|\.)|\bp\s*[=<>]\s*\.?\d',line):
            match=_REPORTED.search(line)
            suggestion=None
            if match:
                name,dfs,value,relation,p=match.groups()
                suggestion={'id':f'statistic_{len(candidates)+1}','kind':'statistic_consistency','test':name,
                            'df':[int(v) for v in dfs.split(',')] if dfs else [],'statistic':value,'reported_p':p,'relation':relation}
                from sra.extended_inspection import prepare_extra
                try:
                    prepare_extra(suggestion,None)
                except ValueError:
                    suggestion=None
            add('statistic',start,start+len(line.rstrip('\r\n')),suggested_check=suggestion)
        if re.search(r'\b(?:Fig(?:ure)?\.?\s+\d+)',line,re.I):
            add('figure',start,start+len(line.rstrip('\r\n')),visual_interpretation_verified=False)
        for match in re.finditer(r'\$([^$\n]{1,256})\$|\\\[([^\n]{1,256})\\\]',line):
            expression=match.group(1) or match.group(2)
            suggestion=None
            if expression.count('=')==1 and not any(c in expression for c in '<>!'):
                left,right=expression.split('=')
                try:
                    tree=ast.parse(left+'+('+right+')',mode='eval')
                    names=sorted({node.id for node in ast.walk(tree) if isinstance(node,ast.Name)}-{'sin','cos','exp','log','sqrt'})
                    suggestion={'id':f'equation_{len(candidates)+1}','kind':'symbolic_identity',
                                'variables':{name:'real' for name in names},'left':left.strip(),'right':right.strip()}
                    from sra.symbolic import prepare_symbolic
                    prepare_symbolic(suggestion)
                except (SyntaxError,ValueError,RecursionError):
                    suggestion=None
            add('equation',start+match.start(),start+match.end(),suggested_check=suggestion)
    candidates.sort(key=lambda row:(row['start'],row['kind']))
    checks=[row['suggested_check'] for row in candidates if row.get('suggested_check') is not None]
    groups=[]
    current=[]
    symbolic_count=0
    for check in checks:
        symbolic=check['kind'].startswith('symbolic_')
        if len(current)==32 or (symbolic and symbolic_count==8):
            groups.append(current)
            current=[]
            symbolic_count=0
        current.append(check)
        symbolic_count+=symbolic
    if current:
        groups.append(current)
    specs=[{'schema_version':'1.0','source_sha256':document.sha256,'extracted_text_sha256':digest(text),'checks':group} for group in groups]
    return {'schema_version':'inspection-preparation/1.0','execution_status':'complete','source_sha256':document.sha256,
            'extracted_text_sha256':digest(text),'checks_executed':False,'candidates':candidates,
            'proposed_toolkit_spec':specs[0] if len(specs)==1 else None,'proposed_toolkit_specs':specs,
            'limitations':['Candidates require confirmation before use as structured checks.',
                           'Inline math, line-based assumptions/statistics, Markdown tables and figure mentions are bounded syntax cues.',
                           'No automatic LaTeX/OCR equation semantics, raster figure interpretation or table-to-data mapping is certified.']}


def inspection_markdown(report):
    from sra.report import _safe_md
    import json
    lines=['# Inspection input preparation','','These candidates require confirmation; no inferred checks were executed.',
           f"Source SHA-256: {report['source_sha256']}",f"Extracted text SHA-256: {report['extracted_text_sha256']}",
           f"Proposed bounded specification batches: {len(report['proposed_toolkit_specs'])}",'']
    for item in report['candidates']:
        lines.extend([f"## {_safe_md(item['id'])}: {_safe_md(item['kind'])} (line {item['line']})",
                      _safe_md(item['source_quote'])])
        if item.get('suggested_check') is not None:
            lines.append(_safe_md(json.dumps(item['suggested_check'],ensure_ascii=False)))
    lines.extend(['','## Limits',*[_safe_md(v) for v in report['limitations']]])
    return '\n'.join(lines)+'\n'
