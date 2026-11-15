"""Interpret directional Crossref update metadata without inferring completeness."""
import hashlib
import json
from decimal import Decimal


def _canonical_snapshot(value,depth=0):
    """Preserve JSON numeric tokens instead of coercing Decimal into strings."""
    if depth>64:
        raise ValueError('Publication metadata exceeds 64 nesting levels.')
    if isinstance(value,dict):
        if any(not isinstance(key,str) for key in value):
            raise ValueError('Publication metadata requires string object keys.')
        return '{'+','.join(json.dumps(key,ensure_ascii=False)+':'+_canonical_snapshot(value[key],depth+1) for key in sorted(value))+'}'
    if isinstance(value,list):
        return '['+','.join(_canonical_snapshot(item,depth+1) for item in value)+']'
    if isinstance(value,Decimal) or type(value) in (int,float):
        number=Decimal(str(value))
        if not number.is_finite():
            raise ValueError('Publication metadata numbers must be finite.')
        return str(number)
    return json.dumps(value,ensure_ascii=False,allow_nan=False)


def summarize_publication(doi,message):
    from sra.doi import normalize_doi
    normalized=normalize_doi(doi)
    if normalized is None or not isinstance(message,dict) or normalize_doi(message.get('DOI'))!=normalized:
        raise ValueError('Publication snapshot must match the requested DOI.')
    events={}
    for field,direction in (('updated-by','updates_this_record'),('update-to','this_record_updates_other')):
        rows=message.get(field)
        if rows is None:
            rows=[]
        if not isinstance(rows,list) or len(rows)>64:
            raise ValueError('Update records must be a bounded list.')
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get('type'),str) or not 1<=len(row['type'])<=80:
                raise ValueError('An update record needs an explicit bounded type.')
            target=normalize_doi(row.get('DOI'))
            if target is None:
                raise ValueError('An update record needs a valid related DOI.')
            kind=row['type'].lower().replace('_','-').replace(' ','-')
            key=(direction,target,kind)
            events[key]={'direction':direction,'doi':target,'type':kind}
    ordered=[events[k] for k in sorted(events)]
    incoming={e['type'] for e in ordered if e['direction']=='updates_this_record'}
    outgoing={e['type'] for e in ordered if e['direction']=='this_record_updates_other'}
    if 'retraction' in incoming:
        status='RETRACTION_REPORTED'
    elif 'partial-retraction' in incoming:
        status='PARTIAL_RETRACTION_REPORTED'
    elif 'withdrawal' in incoming:
        status='WITHDRAWAL_REPORTED'
    elif 'removal' in incoming:
        status='REMOVAL_REPORTED'
    elif incoming & {'expression-of-concern','concern'}:
        status='CONCERN_REPORTED'
    elif incoming & {'correction','erratum','corrigendum'}:
        status='CORRECTION_REPORTED'
    elif incoming:
        status='UPDATES_REPORTED'
    elif 'retraction' in outgoing:
        status='RETRACTION_NOTICE'
    elif 'partial-retraction' in outgoing:
        status='PARTIAL_RETRACTION_NOTICE'
    elif 'withdrawal' in outgoing:
        status='WITHDRAWAL_NOTICE'
    elif 'removal' in outgoing:
        status='REMOVAL_NOTICE'
    elif outgoing:
        status='UPDATE_NOTICE'
    else:
        status='NO_UPDATES_REPORTED'
    canonical=_canonical_snapshot(message)
    return {'meaning':'Directional editorial updates in the supplied Crossref snapshot; metadata coverage and authenticity are not independently established.',
            'doi':normalized,'publication_status':status,'updates':ordered,
            'metadata_sha256':hashlib.sha256(canonical.encode()).hexdigest(),
            'absence_proves_no_updates':False,'record_authenticity_verified':False,
            'scope':'updated-by and update-to fields only; absence is not proof that a publication is current or unretracted.'}


def publication_status(item,backend):
    return 'CANDIDATES',item['summary']
