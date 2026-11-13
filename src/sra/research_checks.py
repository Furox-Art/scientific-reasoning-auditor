"""Conditional research-method checks; never certify empirical scientific truth."""
import itertools
import math
import warnings
from statistics import NormalDist


def _numeric(operation):
    from sra.toolkit import _STATISTICS_LOCK
    with _STATISTICS_LOCK,warnings.catch_warnings(record=True) as alerts:
        warnings.simplefilter('always')
        details=operation()
    def finite(value):
        if isinstance(value,dict):
            return all(finite(v) for v in value.values())
        if isinstance(value,(tuple,list)):
            return all(finite(v) for v in value)
        return math.isfinite(value) if isinstance(value,(int,float)) else True
    if alerts or not finite(details):
        return 'UNDETERMINED',{'meaning':'Numerical warning or nonfinite output; no agreement verdict is issued.'}
    return 'CALCULATED',details


def causal_graph(item,nx):
    def graph(edges):
        result=nx.DiGraph()
        result.add_nodes_from(sorted(item['nodes']))
        result.add_edges_from(sorted(map(tuple,edges)))
        return result
    treatment,outcome=item['treatment'],item['outcome']
    selected=set(item['adjustment'])
    original=graph(item['edges'])
    def valid(g,adjustment):
        if adjustment & nx.descendants(g,treatment):
            return False
        backdoor=g.copy()
        backdoor.remove_edges_from(list(backdoor.out_edges(treatment)))
        return bool(nx.is_d_separator(backdoor,{treatment},{outcome},adjustment))
    accepted=valid(original,selected)
    eligible=sorted(set(item['observed'])-{treatment,outcome}-nx.descendants(original,treatment))
    alternatives=[]
    for size in range(len(eligible)+1):
        alternatives=[list(group) for group in itertools.combinations(eligible,size) if valid(original,set(group))]
        if alternatives:
            break
    details={'meaning':'Selected adjustment meets or violates the backdoor criterion in the declared DAG only; this does not establish real-world causal assumptions.',
             'adjustment_valid':accepted,'backdoor_adjustment_available':bool(alternatives),'smallest_adjustment_sets':alternatives,
             'directed_treatment_outcome_path':bool(nx.has_path(original,treatment,outcome)),
             'model_assumptions_confirmed':False,'effect_estimated':False,
             'other_identification_methods_assessed':False}
    if 'sensitivity_graph_edges' in item:
        details['sensitivity']={'added_edges':item['sensitivity_edges'],
                                'adjustment_valid':valid(graph(item['sensitivity_graph_edges']),selected)}
    return ('VERIFIED' if accepted else 'REFUTED'),details


def bias_assessment(item,backend):
    return 'CANDIDATES',{'meaning':'Evidence-linked caller judgments requiring independent methodological review; not an automated RoB2 assessment.',
        'domains':item['domains'],'concerns_reported':sorted(k for k,v in item['domains'].items() if v['judgment']=='concern'),
        'unknown_domains':sorted(k for k,v in item['domains'].items() if v['judgment']=='unknown'),
        'all_judgments_caller_supplied':True,'expert_certification':False}


def power_analysis(item,backend):
    def calculate():
        independent=item['design']=='independent_t'
        model=backend.TTestIndPower() if independent else backend.TTestPower()
        effect,alpha,ratio=map(float,(item['effect_size'],item['alpha'],item['ratio']))
        options={'effect_size':effect,'alpha':alpha,'alternative':'two-sided'}
        if independent:
            options['ratio']=ratio
        if item['mode']=='sample_size':
            n=math.ceil(float(model.solve_power(power=float(item['target_power']),**options)))
        else:
            n=item['nobs']
        if not 2<=n<=1000000:
            raise ArithmeticError('Required sample size is outside supported limits.')
        details={'meaning':'Prospective two-sided t-test power under explicitly supplied standardized effect and design assumptions; not observed post-hoc power or design certification.',
                 'design':item['design'],'alpha':alpha,'effect_size':effect}
        if independent:
            n2=max(2,math.ceil(n*ratio))
            if n2>1000000:
                raise ArithmeticError('Second group size exceeds supported bounds.')
            options['ratio']=n2/n
            power=float(model.power(nobs1=n,**options))
            details.update(n_group1=n,n_group2=n2,requested_ratio=ratio,effective_ratio=n2/n)
        else:
            power=float(model.power(nobs=n,**options))
            details['n_pairs']=n
        details['power']=power
        if item['mode']=='sample_size' and power<float(item['target_power'])-1e-10:
            raise ArithmeticError('Rounded allocation did not achieve the target power.')
        return details
    status,details=_numeric(calculate)
    if status=='CALCULATED' and 'reported_power' in item:
        agrees=abs(details['power']-float(item['reported_power']))<=1e-6
        status='VERIFIED' if agrees else 'REFUTED'
        details['reported_power_absolute_tolerance']=1e-6
    return status,details


def meta_analysis(item,backend):
    import numpy as np
    def calculate():
        effects=np.array([float(s['effect']) for s in item['studies']])
        variances=np.array([float(s['variance']) for s in item['studies']])
        z=NormalDist().inv_cdf(1-float(item['alpha'])/2)
        def pool(e,v):
            weights=1/v
            fixed=float(np.sum(weights*e)/np.sum(weights))
            q=float(np.sum(weights*(e-fixed)**2))
            df=len(e)-1
            tau=0.0
            if item['model']=='random' and len(e)>1 and q>0:
                if item['tau_method']=='dersimonian_laird':
                    tau=max(0.0,(q-df)/float(np.sum(weights)-np.sum(weights**2)/np.sum(weights)))
                else:
                    fit=backend.combine_effects(e,v,method_re='iterated',maxiter=1000,atol=1e-12)
                    tau=max(0.0,float(fit.tau2))
            weights=1/(v+tau)
            estimate=float(np.sum(weights*e)/np.sum(weights))
            if item['model']=='random' and item['tau_method']=='paule_mandel' and len(e)>1:
                residual_q=float(np.sum(weights*(e-estimate)**2))
                if (tau>0 and abs(residual_q-df)>1e-6*max(1,df)) or (tau==0 and residual_q>df+1e-6):
                    raise ArithmeticError('Between-study variance did not converge.')
            se=math.sqrt(float(1/np.sum(weights)))
            return {'estimate':estimate,'standard_error':se,'confidence_interval':[estimate-z*se,estimate+z*se],
                    'q':q,'tau_squared':tau,'i_squared':max(0.0,(q-df)/q) if q>0 else 0.0}
        pooled=pool(effects,variances)
        leave=[{'omitted_study':study['id'],'estimate':pool(np.delete(effects,i),np.delete(variances,i))['estimate']} for i,study in enumerate(item['studies'])]
        asymmetry={'status':'not_requested'}
        if item.get('asymmetry',False):
            if len(effects)<10 or len(set(variances))<2:
                asymmetry={'status':'undetermined','reason':'Requires >=10 studies and differing precisions.'}
            else:
                from statsmodels.regression.linear_model import OLS
                precision=1/np.sqrt(variances)
                design=np.column_stack([np.ones(len(effects)),precision])
                condition=float(np.linalg.cond(design))
                if not math.isfinite(condition) or condition>1e8:
                    asymmetry={'status':'undetermined','reason':'Egger design is ill-conditioned.',
                               'condition_number':condition if math.isfinite(condition) else None,'condition_limit':1e8}
                else:
                    fit=OLS(effects*precision,design).fit()
                    p_value=float(fit.pvalues[0])
                    if not math.isfinite(p_value) or not 0<p_value<=1:
                        asymmetry={'status':'undetermined','reason':'Egger probability is nonfinite or underflowed; exact zero is not reported.'}
                    else:
                        asymmetry={'status':'calculated','egger_intercept':float(fit.params[0]),'p_value':p_value,
                                   'interpretation':'Small-study asymmetry diagnostic, not proof of publication bias.'}
        return {'meaning':'Pooling on the declared common effect scale with normal-approximation confidence intervals; independence, comparable estimands and study validity remain unverified.',
                **pooled,'effect_scale':item['effect_scale'],'model':item['model'],'tau_method':item['tau_method'],
                'leave_one_out':leave,'asymmetry':asymmetry,'publication_bias_proven':False}
    status,details=_numeric(calculate)
    if status=='CALCULATED' and details['asymmetry']['status']=='undetermined':
        status='UNDETERMINED'
    return status,details


def bayesian_diagnostics(item,backend):
    import numpy as np
    def calculate():
        chains=np.asarray(item['chains'],dtype=float)
        api=backend
        axes={}
        if backend.__name__=='arviz_stats':
            from arviz_stats.base import array_stats
            api=array_stats
            axes={'chain_axis':0,'draw_axis':1}
        rhat=float(api.rhat(chains,method='rank',**axes))
        bulk=float(api.ess(chains,method='bulk',**axes))
        tail=float(api.ess(chains,method='tail',prob=(.05,.95),**axes))
        flags=[]
        if rhat>float(item['rhat_max']):
            flags.append('rhat_exceeds_threshold')
        if min(bulk,tail)<float(item['ess_min']):
            flags.append('ess_below_threshold')
        return {'meaning':'Rank-normalized R-hat and bulk/tail effective sample-size diagnostics on supplied draws; passing thresholds does not prove convergence or posterior correctness.',
                'rhat':rhat,'ess_bulk':bulk,'ess_tail':tail,'rhat_max':float(item['rhat_max']),
                'ess_min':float(item['ess_min']),'tail_probabilities':[.05,.95],'flags':flags,'posterior_correctness_proven':False}
    return _numeric(calculate)


def ml_validation(item,backend):
    samples={s['id']:s for s in item['samples']}
    splits={k:set(v) for k,v in item['splits'].items()}
    violations=[]
    facts=[]
    unassessed=[]
    for (a,left),(b,right) in itertools.combinations(sorted(splits.items()),2):
        shared=left&right
        if shared:
            violations.append('sample_overlap')
            facts.append({'partitions':[a,b],'shared_sample_count':len(shared),'examples':sorted(shared)[:20]})
        if item.get('group_exclusive',False):
            if any(samples[s]['group'] is None for s in left|right):
                unassessed.append('missing_group_ids')
            groups={samples[s]['group'] for s in left if samples[s]['group'] is not None}&{samples[s]['group'] for s in right if samples[s]['group'] is not None}
            if groups:
                violations.append('group_overlap')
                facts.append({'partitions':[a,b],'shared_group_count':len(groups)})
    if 'preprocessing_fit_ids' in item:
        leaked=set(item['preprocessing_fit_ids'])-splits['train']
        if leaked:
            violations.append('preprocessing_fit_outside_train')
            facts.append({'fit_outside_train_count':len(leaked),'examples':sorted(leaked)[:20]})
    else:
        unassessed.append('preprocessing_fit_not_supplied')
    if item.get('temporal',False):
        order=[name for name in ('train','validation','test') if name in splits]
        for a,b in zip(order,order[1:]):
            values=[[samples[s]['time'] for s in splits[name]] for name in (a,b)]
            if any(v is None for group in values for v in group):
                unassessed.append('missing_timestamps')
            else:
                from decimal import Decimal
                if max(map(Decimal,values[0]))>=min(map(Decimal,values[1])):
                    violations.append('temporal_order_violation')
    return 'CANDIDATES',{'meaning':'Mechanical review of declared inductive train/validation/test manifests; actual preprocessing code, measurement timing and generalization remain unverified.',
        'protocol_status':'violations_found' if violations else 'no_violations_detected',
        'violations':sorted(set(violations)),'unassessed_checks':sorted(set(unassessed)),
        'facts':facts,'pipeline_correctness_proven':False}
