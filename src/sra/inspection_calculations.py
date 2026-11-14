"""Numerical diagnostics and explicitly non-semantic evidence inspection."""
import math
from bisect import bisect_right
import re
import warnings
from decimal import Context,Decimal,localcontext
from xml.etree import ElementTree


def statistic_consistency(item,stats):
    from sra.toolkit import _STATISTICS_LOCK
    with localcontext(Context(prec=256)):
        statistic=Decimal(item['statistic'])
        half=Decimal(1).scaleb(statistic.as_tuple().exponent)/2
        low,high=statistic-half,statistic+half
        if item['test'] in ('t','z'):
            low,high=(Decimal(0) if low<=0<=high else min(abs(low),abs(high))),max(abs(low),abs(high))
        else:
            low=max(Decimal(0),low)
        with _STATISTICS_LOCK,warnings.catch_warnings(record=True) as alerts:
            warnings.simplefilter('always')
            def survival(value):
                if item['test']=='t':
                    return 2*float(stats.t.sf(float(value),item['df'][0]))
                if item['test']=='z':
                    return 2*float(stats.norm.sf(float(value)))
                distribution=stats.f if item['test']=='F' else stats.chi2
                return float(distribution.sf(float(value),*item['df']))
            p_low,p_high=survival(high),survival(low)
        details={'meaning':'Reported statistic/p-value consistency with two-sided t/z or upper-tail F/chi-square and rounding intervals; study validity is unverified.',
                 'computed_p_interval':[p_low,p_high],'statistic_interval':[str(low),str(high)]}
        if alerts or not all(math.isfinite(v) and v>0 for v in (p_low,p_high)):
            return 'UNDETERMINED',{'meaning':'Numerical warning or unresolved tail underflow; no consistency verdict.'}
        p=Decimal(item['reported_p'])
        p_half=Decimal(1).scaleb(p.as_tuple().exponent)/2
        margin=8*max(math.ulp(p_low),math.ulp(p_high),math.ulp(float(p)))
        relation=item['relation']
        if relation=='=':
            a,b=float(max(Decimal(0),p-p_half)),float(min(Decimal(1),p+p_half))
            verified=p_low>=a+margin and p_high<=b-margin
            refuted=p_high<a-margin or p_low>b+margin
            details['reported_p_interval']=[a,b]
        else:
            threshold=float(p)
            verified=p_high<threshold-margin if relation=='<' else p_low>threshold+margin
            refuted=p_low>threshold+margin if relation=='<' else p_high<threshold-margin
        return ('VERIFIED' if verified else 'REFUTED' if refuted else 'UNDETERMINED'),details


def statistical_analysis(item,stats):
    from sra.toolkit import _STATISTICS_LOCK
    operation=item['operation']
    meaning='Calculated on supplied data; test choice, missingness mechanism and distributional assumptions are not proven.'
    if operation=='multiple_testing':
        with localcontext(Context(prec=80)):
            values=list(map(Decimal,item['p_values']))
            order=sorted(range(len(values)),key=lambda i:(values[i],i))
            n=len(values)
            corrected=[Decimal(0)]*n
            running=Decimal(0) if item['method']=='holm' else Decimal(1)
            indices=reversed(range(n)) if item['method']=='benjamini_hochberg' else range(n)
            for rank in indices:
                index=order[rank]
                factor=Decimal(n)/Decimal(rank+1) if item['method']=='benjamini_hochberg' else Decimal(n-rank if item['method']=='holm' else n)
                value=min(Decimal(1),values[index]*factor)
                running=min(running,value) if item['method']=='benjamini_hochberg' else max(running,value) if item['method']=='holm' else value
                corrected[index]=running
        return 'CALCULATED',{'meaning':meaning,'method':item['method'],'adjusted_p_values':[str(v) for v in corrected]}
    with _STATISTICS_LOCK,warnings.catch_warnings(record=True) as alerts:
        warnings.simplefilter('always')
        if operation=='linear_regression':
            pairs=list(zip(item['x'],item['y']))
            complete=[(float(x),float(y)) for x,y in pairs if x is not None and y is not None]
            missing=len(pairs)-len(complete)
            if (missing and item['missing_policy']=='report') or len(complete)<3:
                return 'UNDETERMINED',{'meaning':meaning,'missing_pairs':missing,'complete_pairs':len(complete),'missing_policy':item['missing_policy']}
            x,y=zip(*complete)
            result=stats.linregress(x,y,alternative='two-sided')
            computed={'slope':float(result.slope),'intercept':float(result.intercept),'r_squared':float(result.rvalue**2),
                      'p_value':float(result.pvalue),'slope_standard_error':float(result.stderr)}
            details={'meaning':meaning,'computed':computed,'missing_pairs':missing,'complete_pairs':len(complete),'missing_policy':item['missing_policy']}
        else:
            groups=[[float(v) for v in g] for g in item['groups']]
            normality=[stats.shapiro(g) for g in groups]
            variance=stats.levene(*groups,center='median')
            computed={'shapiro_p_values':[float(r.pvalue) for r in normality],'levene_p_value':float(variance.pvalue)}
            details={'meaning':meaning,'computed':computed,'assumptions_proven':False,
                     'interpretation':'Failure to reject is not proof of normality or equal variance; independence needs study-design review.'}
    values=[v for value in computed.values() for v in (value if isinstance(value,list) else [value])]
    p_values=[v for key,value in computed.items() if 'p_value' in key for v in (value if isinstance(value,list) else [value])]
    if alerts or any(not math.isfinite(v) for v in values) or any(v==0 for v in p_values):
        return 'UNDETERMINED',{'meaning':'Numerical warning, nonfinite output or unresolved zero p-value; no agreement verdict.'}
    return 'CALCULATED',details


def context_matches(claim,sources,fuzz,limit=5):
    matches=[]
    for source in sources:
        text=source['text']
        # Sentence/line windows are retrieval units, not semantic claims.
        line_starts=[0]+[m.end() for m in re.finditer('\n',text)]
        segments=re.finditer(r'[^.!?\n]+[.!?]*',text)
        for segment in segments:
            start=segment.start()
            while start<segment.end():
                end=min(start+800,segment.end())
                quote=text[start:end]
                if quote.strip():
                    if len(matches)>=2000:
                        raise ValueError('Context retrieval exceeds 2000 candidate windows; split sources explicitly.')
                    context_start=max(0,start-200)
                    context_end=min(len(text),end+200)
                    matches.append({'source_id':source['id'],'source_sha256':source['sha256'],
                        'start':start,'end':end,'line':bisect_right(line_starts,start),'passage':quote,
                        'context_start':context_start,'context_end':context_end,'context':text[context_start:context_end],
                        'similarity':float(fuzz.token_set_ratio(claim,quote)),
                        'negation_cues':re.findall(r'\b(?:not|no|never|without|failed)\b',quote,re.I),
                        'direction_cues':re.findall(r'\b(?:increase\w*|decrease\w*|reduc\w*|improv\w*)\b',quote,re.I),
                        'requires_review':True})
                if end==segment.end():
                    break
                start=end-100
    matches.sort(key=lambda row:(-row['similarity'],row['source_id'],row['start']))
    return matches[:limit]


def citation_context(item,fuzz):
    return 'CANDIDATES',{'meaning':'Local sentence/context retrieval with lexical review cues; negation and direction cues are not contradiction judgments.',
                         'support_status':'NOT_ASSESSED','matches':context_matches(item['claim'],item['sources'],fuzz)}


def table_compare(item,backend):
    from sra.toolkit_spec import number,digest
    (left_header,left),(right_header,right)=item['tables']
    mismatches=[]
    if set(left_header)!=set(right_header):
        mismatches.append({'kind':'column_set_mismatch'})
    for key in sorted(set(left)|set(right)):
        if key not in left or key not in right:
            mismatches.append({'kind':'missing_row','key':list(key),'missing_from':'table' if key not in left else 'supplement'})
            continue
        for column in sorted(set(left_header)&set(right_header)-set(item['keys'])):
            a,b=left[key][column],right[key][column]
            try:
                with localcontext(Context(prec=256)):
                    agrees=abs(number(a)-number(b))<=Decimal(item['atol'])
            except ValueError:
                agrees=a==b
            if not agrees:
                mismatches.append({'kind':'cell_mismatch','key':list(key),'column':column,'table':a,'supplement':b})
    return ('REFUTED' if mismatches else 'VERIFIED'),{
        'meaning':'Keyed cell agreement on explicitly supplied CSV snapshots; no authenticity or manuscript-to-table mapping proof.',
        'table_sha256':digest(item['table_csv']),'supplement_sha256':digest(item['supplement_csv']),
        'table_rows':len(left),'supplement_rows':len(right),'mismatch_count':len(mismatches),
        'mismatches':mismatches[:100],'mismatches_truncated':len(mismatches)>100,'atol':item['atol']}


def figure_svg(item,backend):
    from sra.toolkit_spec import digest
    try:
        root=ElementTree.fromstring(item['svg'])
    except ElementTree.ParseError as exc:
        raise ValueError('Malformed SVG.') from exc
    if root.tag.split('}')[-1]!='svg':
        raise ValueError('Expected an SVG root.')
    nodes=list(root.iter())
    if len(nodes)>2000:
        raise ValueError('SVG exceeds 2000 nodes.')
    texts=[''.join(node.itertext()).strip() for node in nodes if node.tag.split('}')[-1] in ('text','title','desc')]
    shapes={name:sum(node.tag.split('}')[-1]==name for node in nodes) for name in ('path','polyline','polygon','circle','rect')}
    def active(node):
        tag=node.tag.split('}')[-1].lower()
        if tag in ('script','image','foreignobject','animate','set'):
            return True
        for key,value in node.attrib.items():
            name=key.split('}')[-1].lower()
            if name=='href' or name.startswith('on') or (name=='style' and re.search(r'url\s*\(|@import|javascript\s*:',value,re.I)):
                return True
        return tag=='style' and bool(re.search(r'url\s*\(|@import|javascript\s*:',''.join(node.itertext()),re.I))
    external=any(active(node) for node in nodes)
    return 'CANDIDATES',{'meaning':'SVG labels and structural inventory only; no rendering, scripts, URLs or external resources are loaded.',
        'source_sha256':digest(item['svg']),'text_labels':texts,'shape_counts':shapes,'view_box':root.get('viewBox'),
        'external_or_active_content_present':external,'active_content_inventory_complete':False,'scientific_visual_interpretation_verified':False,
        'review_questions':['Check axis units, scales, uncertainty, sample sizes and agreement with supplied tables.',
                            'Raster images, curve digitization and scientific figure interpretation remain unverified.']}
