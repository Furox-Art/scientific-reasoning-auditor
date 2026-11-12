"""Extra toolkit validators; all preflight remains dependency-independent."""
import csv
import io
import re

EXTRA_KINDS=('symbolic_identity','symbolic_derivative','symbolic_antiderivative',
             'statistical_analysis','citation_context','table_compare','figure_svg','statistic_consistency')


def csv_table(text,keys):
    from sra.toolkit_spec import _text
    try:
        rows=list(csv.reader(io.StringIO(_text(text,200000)),strict=True))
    except csv.Error as exc:
        raise ValueError('Malformed or oversized CSV field.') from exc
    if not 2<=len(rows)<=1001 or not 1<=len(rows[0])<=32 or any(not c.strip() for c in rows[0]) or len(set(rows[0]))!=len(rows[0]):
        raise ValueError('CSV needs distinct nonempty headers, 1..32 columns and 1..1000 data rows.')
    header=rows[0]
    if not isinstance(keys,list) or not keys or any(k not in header for k in keys) or len(set(keys))!=len(keys):
        raise ValueError('Declare distinct existing CSV key columns.')
    result={}
    for row in rows[1:]:
        if len(row)!=len(header):
            raise ValueError('CSV row width differs from header.')
        value=dict(zip(header,row))
        key=tuple(value[k] for k in keys)
        if key in result or any(not v.strip() for v in key):
            raise ValueError('CSV keys must be nonempty and unique.')
        result[key]=value
    return header,result


def prepare_extra(item,document):
    from sra.toolkit_spec import _fields,_text,number,digest,_NAME
    from sra.document import SourceIdentityError
    kind=item['kind']
    base=('id','kind')
    result=dict(item)
    if kind.startswith('symbolic_'):
        from sra.symbolic import prepare_symbolic
        return prepare_symbolic(item)
    if kind=='statistic_consistency':
        _fields(item,base+('test','statistic','df','reported_p'),('relation',))
        df=item['df']
        counts={'t':1,'F':2,'z':0,'chi2':1}
        if not isinstance(item['test'],str) or item['test'] not in counts or not isinstance(df,list) or len(df)!=counts[item['test']] or any(type(v) is not int or not 1<=v<=1000000 for v in df):
            raise ValueError('Statistic test or exact degrees of freedom are unsupported.')
        result.update(statistic=str(number(item['statistic'])),reported_p=str(number(item['reported_p'])),relation=item.get('relation','='))
        if not 0<=number(result['reported_p'])<=1 or result['relation'] not in ('=','<','>') or (item['test'] in ('F','chi2') and number(result['statistic'])<0):
            raise ValueError('Unsupported reported statistic or p-value relation.')
    elif kind=='statistical_analysis':
        operation=item.get('operation')
        if operation=='linear_regression':
            _fields(item,base+('operation','x','y'),('missing_policy',))
            x,y=item['x'],item['y']
            if not isinstance(x,list) or not isinstance(y,list) or len(x)!=len(y) or not 3<=len(x)<=2000:
                raise ValueError('Regression needs 3..2000 paired observations.')
            policy=item.get('missing_policy','report')
            if policy not in ('report','complete_case'):
                raise ValueError('missing_policy must be report or complete_case.')
            result.update(x=[None if v is None else str(number(v)) for v in x],y=[None if v is None else str(number(v)) for v in y],missing_policy=policy)
        elif operation=='multiple_testing':
            _fields(item,base+('operation','p_values','method'))
            values=item['p_values']
            if not isinstance(values,list) or not 1<=len(values)<=2000 or item['method'] not in ('holm','bonferroni','benjamini_hochberg'):
                raise ValueError('Supply 1..2000 p-values and a supported correction.')
            result['p_values']=[str(number(v)) for v in values]
            if any(not 0<=number(v)<=1 for v in result['p_values']):
                raise ValueError('p-values must be in [0,1].')
        elif operation=='assumption_diagnostics':
            _fields(item,base+('operation','groups'))
            groups=item['groups']
            if not isinstance(groups,list) or not 2<=len(groups)<=8 or any(not isinstance(g,list) or not 3<=len(g)<=2000 for g in groups) or sum(map(len,groups))>10000:
                raise ValueError('Diagnostics require 2..8 groups, 3..2000 values each, at most 10000 values.')
            result['groups']=[[str(number(v)) for v in g] for g in groups]
        else:
            raise ValueError('Unsupported statistical analysis operation.')
    elif kind=='citation_context':
        _fields(item,base+('claim','sources'))
        _text(item['claim'],2000)
        if document is not None and item['claim'] not in document.text:
            raise SourceIdentityError('Context query is absent from manuscript.')
        sources=item['sources']
        if not isinstance(sources,list) or not 1<=len(sources)<=8:
            raise ValueError('Supply 1..8 local sources.')
        seen=set()
        for row in sources:
            _fields(row,('id','text','sha256'))
            if not isinstance(row['id'],str) or not _NAME.fullmatch(row['id']) or row['id'] in seen:
                raise ValueError('Source IDs must be distinct simple names.')
            seen.add(row['id'])
            if digest(_text(row['text'],100000))!=row['sha256']:
                raise ValueError('Context source hash mismatch.')
    elif kind=='table_compare':
        _fields(item,base+('table_csv','supplement_csv','keys'),('atol',))
        result['tables']=[csv_table(item[key],item['keys']) for key in ('table_csv','supplement_csv')]
        result['atol']=str(number(item.get('atol','0')))
        if number(result['atol'])<0:
            raise ValueError('Tolerance must be nonnegative.')
    else:
        _fields(item,base+('svg',))
        text=_text(item['svg'],200000)
        if re.search(r'<!\s*(?:DOCTYPE|ENTITY)',text,re.I):
            raise ValueError('SVG declarations and entities are forbidden.')
    return result
