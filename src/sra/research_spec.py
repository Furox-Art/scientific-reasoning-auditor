"""Dependency-independent preflight for explicit research-method inputs."""
RESEARCH_KINDS=('causal_graph','bias_assessment','power_analysis','meta_analysis',
                'bayesian_diagnostics','ml_validation','publication_status')
BIAS_DOMAINS=('randomization','allocation_concealment','blinding','missing_outcomes','selective_reporting')


def _dag(nodes,edges):
    from sra.toolkit_spec import _NAME
    if not isinstance(nodes,list) or not 2<=len(nodes)<=10 or any(not isinstance(n,str) or not _NAME.fullmatch(n) for n in nodes) or len(set(nodes))!=len(nodes):
        raise ValueError('Declare 2..10 distinct graph nodes.')
    if not isinstance(edges,list) or len(edges)>32 or any(not isinstance(e,list) or len(e)!=2 or any(n not in nodes for n in e) or e[0]==e[1] for e in edges) or len({tuple(e) for e in edges})!=len(edges):
        raise ValueError('Declare at most 32 distinct directed edges between declared nodes.')
    remaining=set(nodes)
    while remaining:
        roots={n for n in remaining if not any(b==n and a in remaining for a,b in edges)}
        if not roots:
            raise ValueError('A causal graph must be acyclic.')
        remaining-=roots


def prepare_research(item,document):
    from sra.toolkit_spec import _fields,_text,_NAME,number
    from sra.document import SourceIdentityError
    kind=item['kind']
    base=('id','kind')
    result=dict(item)
    def numeric(value,low,high,strict=False):
        parsed=number(value)
        from decimal import Decimal
        low,high=Decimal(str(low)),Decimal(str(high))
        if not (low<parsed<high if strict else low<=parsed<=high):
            raise ValueError('Research-method numeric value is outside its supported range.')
        return str(parsed)
    def names(values,allowed):
        allowed=set(allowed)
        if not isinstance(values,list) or any(not isinstance(v,str) or v not in allowed for v in values) or len(set(values))!=len(values):
            raise ValueError('Expected distinct declared identifiers.')
        return values
    if kind=='causal_graph':
        _fields(item,base+('nodes','edges','treatment','outcome','observed','adjustment'),('sensitivity_edges',))
        nodes=item['nodes']
        _dag(nodes,item['edges'])
        treatment,outcome=item['treatment'],item['outcome']
        if treatment not in nodes or outcome not in nodes or treatment==outcome:
            raise ValueError('Treatment and outcome must be different graph nodes.')
        observed=names(item['observed'],nodes)
        adjustment=names(item['adjustment'],observed)
        if treatment not in observed or outcome not in observed or treatment in adjustment or outcome in adjustment:
            raise ValueError('Observed nodes must include treatment/outcome; adjustment must exclude them.')
        if 'sensitivity_edges' in item:
            extra=item['sensitivity_edges']
            _dag(nodes,extra)
            combined=[list(e) for e in sorted({tuple(e) for e in item['edges']+extra})]
            _dag(nodes,combined)
            result['sensitivity_graph_edges']=combined
    elif kind=='bias_assessment':
        _fields(item,base+('domains',))
        _fields(item['domains'],BIAS_DOMAINS)
        for domain,row in item['domains'].items():
            _fields(row,('judgment','source_quote'),('note',))
            if row['judgment'] not in ('concern','no_concern','unknown'):
                raise ValueError('Bias judgment must be concern, no_concern or unknown.')
            quote=row['source_quote']
            if quote is not None:
                _text(quote,2000)
                if document is not None and quote not in document.text:
                    raise SourceIdentityError('Bias evidence quotation is absent from the manuscript.')
            elif row['judgment']!='unknown':
                raise ValueError('A non-unknown bias judgment requires an explicit source quotation.')
            if 'note' in row:
                _text(row['note'],2000)
    elif kind=='power_analysis':
        mode=item.get('mode')
        _fields(item,base+('design','mode','effect_size','alpha')+(('nobs',) if mode=='calculate' else ('target_power',)),('ratio','reported_power'))
        if item['design'] not in ('independent_t','paired_t') or mode not in ('calculate','sample_size'):
            raise ValueError('Supported power designs are independent_t/paired_t with calculate/sample_size mode.')
        result['effect_size']=numeric(item['effect_size'],0,10,True)
        result['alpha']=numeric(item['alpha'],0,.5,True)
        result['ratio']=numeric(item.get('ratio',1),.01,100)
        if item['design']=='paired_t' and number(result['ratio'])!=1:
            raise ValueError('Paired power analysis does not accept an allocation ratio.')
        if mode=='calculate':
            if type(item['nobs']) is not int or not 2<=item['nobs']<=1000000:
                raise ValueError('nobs must be an integer between 2 and 1000000.')
        else:
            result['target_power']=numeric(item['target_power'],0,.9999,True)
            if number(result['target_power'])<=number(result['alpha']):
                raise ValueError('Target power must exceed alpha.')
        if 'reported_power' in item:
            result['reported_power']=numeric(item['reported_power'],0,1)
    elif kind=='meta_analysis':
        _fields(item,base+('studies','effect_scale','model'),('tau_method','alpha','asymmetry','ci_method'))
        if item['effect_scale'] not in ('mean_difference','standardized_mean_difference','log_risk_ratio','log_odds_ratio') or item['model'] not in ('fixed','random') or item.get('tau_method','paule_mandel') not in ('paule_mandel','dersimonian_laird'):
            raise ValueError('Declare a common supported effect scale, model and variance estimator.')
        if item.get('ci_method','normal') not in ('normal','modified_hksj') or (item.get('ci_method')=='modified_hksj' and item['model']!='random'):
            raise ValueError('ci_method must be normal, or modified_hksj with a random-effects model.')
        studies=item['studies']
        if not isinstance(studies,list) or not 2<=len(studies)<=50:
            raise ValueError('Meta-analysis requires 2..50 independent study estimates.')
        seen=set()
        normalized=[]
        for row in studies:
            _fields(row,('id','effect','variance'))
            if not isinstance(row['id'],str) or not _NAME.fullmatch(row['id']) or row['id'] in seen:
                raise ValueError('Study identifiers must be distinct simple names.')
            seen.add(row['id'])
            variance=numeric(row['variance'],1e-12,1e12)
            normalized.append({**row,'effect':numeric(row['effect'],-1e6,1e6),'variance':variance})
        if type(item.get('asymmetry',False)) is not bool:
            raise ValueError('asymmetry must be boolean.')
        result.update(studies=normalized,tau_method=item.get('tau_method','paule_mandel'),alpha=numeric(item.get('alpha','.05'),.001,.2),
                      ci_method=item.get('ci_method','normal'))
    elif kind=='bayesian_diagnostics':
        _fields(item,base+('chains',),('rhat_max','ess_min'))
        chains=item['chains']
        if not isinstance(chains,list) or not 2<=len(chains)<=8 or any(not isinstance(c,list) or not 20<=len(c)<=5000 for c in chains) or len({len(c) for c in chains})!=1 or sum(map(len,chains))>20000:
            raise ValueError('Supply 2..8 equal-length chains, 20..5000 draws each and <=20000 total draws.')
        result.update(chains=[[numeric(v,-1e100,1e100) for v in c] for c in chains],
                      rhat_max=numeric(item.get('rhat_max','1.01'),1,2),ess_min=numeric(item.get('ess_min',400),1,20000))
    elif kind=='ml_validation':
        _fields(item,base+('samples','splits'),('preprocessing_fit_ids','group_exclusive','temporal'))
        samples=item['samples']
        if not isinstance(samples,list) or not 2<=len(samples)<=5000:
            raise ValueError('Supply 2..5000 sample manifest records.')
        ids=[]
        normalized=[]
        for row in samples:
            _fields(row,('id',),('group','time'))
            ident=_text(row['id'],64)
            if ident in ids:
                raise ValueError('Sample record IDs must be unique.')
            ids.append(ident)
            group=row.get('group')
            if group is not None:
                _text(group,64)
            normalized.append({'id':ident,'group':group,'time':numeric(row['time'],-1e12,1e12) if row.get('time') is not None else None})
        _fields(item['splits'],('train','test'),('validation',))
        for split,values in item['splits'].items():
            names(values,ids)
            if not values:
                raise ValueError('Declared partitions must be nonempty.')
        if 'preprocessing_fit_ids' in item:
            names(item['preprocessing_fit_ids'],ids)
        if any(type(item.get(key,False)) is not bool for key in ('group_exclusive','temporal')):
            raise ValueError('Manifest check switches must be boolean.')
        result['samples']=normalized
    else:
        _fields(item,base+('doi','message'))
        from sra.publication import summarize_publication
        result['summary']=summarize_publication(item['doi'],item['message'])
    return result
