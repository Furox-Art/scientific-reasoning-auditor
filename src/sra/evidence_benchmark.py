"""Frozen human-rationale retrieval evaluation; never semantic certification."""
import hashlib
import json
from pathlib import Path

from sra.inspection_calculations import context_matches
from sra.json_utils import reject_duplicate_keys
from sra.toolkit_spec import digest


def _read_rows(path,maximum):
    with Path(path).open('rb') as stream:
        raw=stream.read(maximum+1)
    if not raw or len(raw)>maximum:
        raise ValueError('Benchmark file is empty or exceeds its byte limit.')
    rows=[json.loads(line,object_pairs_hook=reject_duplicate_keys) for line in raw.decode('utf-8').splitlines() if line.strip()]
    if not rows or len(rows)>10000 or any(not isinstance(row,dict) for row in rows):
        raise ValueError('Benchmark requires 1..10000 JSON objects.')
    return rows,hashlib.sha256(raw).hexdigest()


def evaluate_scifact(corpus_path,claims_path):
    from rapidfuzz import fuzz,__version__
    records,corpus_hash=_read_rows(corpus_path,40000000)
    claims,claims_hash=_read_rows(claims_path,4000000)
    corpus={}
    for row in records:
        ident=row.get('doc_id')
        abstract=row.get('abstract')
        if type(ident) is not int or ident in corpus or not isinstance(abstract,list) or not 1<=len(abstract)<=1000 or any(not isinstance(s,str) or not s.strip() or len(s)>10000 for s in abstract):
            raise ValueError('Invalid or repeated corpus document.')
        text='\n'.join(abstract)
        if len(text)>100000:
            raise ValueError('Benchmark abstract exceeds 100000 characters.')
        offsets=[]
        start=0
        for sentence in abstract:
            offsets.append((start,start+len(sentence)))
            start+=len(sentence)+1
        corpus[ident]=({'id':f'doc_{ident}','text':text,'sha256':digest(text)},offsets)
    counts={str(k):{'gold_hits':0,'gold_total':0,'positive_windows':0,'returned_windows':0} for k in (1,3,5)}
    seen=set()
    cases=[]
    outside_cited=0
    for claim in sorted(claims,key=lambda c:c.get('id',-1)):
        ident=claim.get('id')
        evidence=claim.get('evidence')
        cited=claim.get('cited_doc_ids')
        if type(ident) is not int or ident in seen or not isinstance(claim.get('claim'),str) or not 1<=len(claim['claim'])<=2000 or not isinstance(evidence,dict) or not isinstance(cited,list) or any(type(v) is not int for v in cited):
            raise ValueError('Invalid or repeated benchmark claim.')
        seen.add(ident)
        gold=set()
        labels=set()
        for doc,rationales in evidence.items():
            if not doc.isdecimal() or int(doc) not in corpus or not isinstance(rationales,list) or not rationales:
                raise ValueError('Invalid gold evidence document.')
            for rationale in rationales:
                if not isinstance(rationale,dict) or rationale.get('label') not in ('SUPPORT','CONTRADICT') or not isinstance(rationale.get('sentences'),list) or not rationale['sentences']:
                    raise ValueError('Invalid human rationale label.')
                labels.add(rationale['label'])
                for sentence in rationale['sentences']:
                    if type(sentence) is not int or not 0<=sentence<len(corpus[int(doc)][1]):
                        raise ValueError('Gold sentence index is outside its source.')
                    gold.add((int(doc),sentence))
        if not gold:
            continue
        document_ids=sorted(set(cited))
        outside_cited+=sum(doc not in document_ids for doc,_ in gold)
        if len(document_ids)>32 or any(doc not in corpus for doc in document_ids):
            raise ValueError('Missing or excessive cited documents.')
        ranked=context_matches(claim['claim'],[corpus[doc][0] for doc in document_ids],fuzz)
        per_case={}
        for k,totals in counts.items():
            selected=ranked[:int(k)]
            hits=set()
            positive=0
            for match in selected:
                doc=int(match['source_id'].removeprefix('doc_'))
                overlapping=set()
                for gold_doc,sentence in gold:
                    a,b=corpus[gold_doc][1][sentence]
                    if doc==gold_doc and match['start']<b and match['end']>a:
                        overlapping.add((gold_doc,sentence))
                hits.update(overlapping)
                positive+=bool(overlapping)
            totals['gold_hits']+=len(hits)
            totals['gold_total']+=len(gold)
            totals['positive_windows']+=positive
            totals['returned_windows']+=len(selected)
            per_case[k]=len(hits)
        cases.append({'claim_id':ident,'gold_sentence_count':len(gold),'gold_labels':sorted(labels),'retrieved_gold_overlap_counts':per_case})
    if not cases:
        raise ValueError('No claims with human rationale labels were supplied.')
    metrics={k:{**v,'gold_sentence_overlap_recall':v['gold_hits']/v['gold_total'],
                  'window_overlap_precision':v['positive_windows']/v['returned_windows'] if v['returned_windows'] else None} for k,v in counts.items()}
    report={'schema_version':'evidence-retrieval-benchmark/1.0','execution_status':'complete',
        'dataset':'SciFact supplied split','corpus_sha256':corpus_hash,'claims_sha256':claims_hash,
        'backend':'RapidFuzz','backend_version':__version__,'claims_in_file':len(claims),
        'claims_with_gold_evidence':len(cases),'claims_without_gold_excluded':len(claims)-len(cases),
        'corpus_documents':len(corpus),'retrieval':metrics,'cases':cases,
        'candidate_scope':'supplied_cited_documents_only','gold_sentences_outside_cited_documents':outside_cited,
        'semantic_verification':{'predictions':0,'abstentions':len(claims),'coverage':0,'accuracy':None},
        'attribution':{'source':'https://github.com/allenai/scifact','claims_and_annotations_license':'CC BY 4.0','abstract_database_license':'ODC-By 1.0'},
        'limitations':['Ranking is restricted to supplied cited documents, not unrestricted literature search.',
            'Overlap means a returned character window intersects a gold sentence; it is not full rationale recovery or semantic correctness.',
            'Unlabelled claims are excluded from retrieval denominators, and all semantic classifications abstain.',
            'No multi-field scientific-error accuracy or independent expert certification follows from this retrieval benchmark.']}
    report['report_sha256']=digest(json.dumps(report,sort_keys=True,allow_nan=False))
    return report


def benchmark_markdown(report):
    lines=['# Real-paper evidence retrieval benchmark','',f"Claims: {report['claims_in_file']}; with gold evidence: {report['claims_with_gold_evidence']}",
           f"Corpus SHA-256: {report['corpus_sha256']}",f"Claims SHA-256: {report['claims_sha256']}",'',
           '| k | Gold sentence overlap recall | Window overlap precision |','|---|---|---|']
    lines.extend(f"| {k} | {v['gold_sentence_overlap_recall']:.4f} | {v['window_overlap_precision']} |" for k,v in report['retrieval'].items())
    lines.extend(['','Semantic prediction coverage: 0. Accuracy: not measured.','',*report['limitations']])
    return '\n'.join(lines)+'\n'
