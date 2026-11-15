"""Conditional grouped-effects REML, enumerated bootstrap and cluster-mean planning."""
import itertools
import math


def multilevel_meta_analysis(item, stats):
    import numpy as np
    from scipy.linalg import cho_factor, cho_solve, solve_triangular
    from scipy.optimize import minimize_scalar, brentq
    from sra.dependent_checks import _guarded, _unknown, _collapsed

    def calculate():
        if _collapsed([s['effect'] for s in item['studies']]):
            return _unknown('input_values_collapse_in_float64')
        values=np.asarray([s['effect'] for s in item['studies']],dtype=float)
        location=float(values[0]);y=values-location
        v=np.asarray(item['covariance'],dtype=float)
        try:
            cho_factor(v,lower=True)
        except np.linalg.LinAlgError:
            return _unknown('sampling_covariance_not_positive_definite')
        if float(np.linalg.cond(v))>1e10:
            return _unknown('ill_conditioned_sampling_covariance')
        groups=sorted({s['group'] for s in item['studies']})
        z=np.asarray([[float(s['group']==g) for g in groups] for s in item['studies']])
        b=z@z.T;ones=np.ones(len(y));scale=float(np.median(np.diag(v)))
        upper=float(item['tau2_max']);bound=math.log1p(upper/scale)
        contrasts=np.zeros((len(y),len(y)-1))
        for j in range(1,len(y)):
            contrasts[:j,j-1]=1/math.sqrt(j*(j+1))
            contrasts[j,j-1]=-j/math.sqrt(j*(j+1))
        vc=contrasts.T@v@contrasts;bc=contrasts.T@b@contrasts;yc=contrasts.T@y

        def evaluate(coordinate):
            tau=scale*math.expm1(float(coordinate));matrix=v+tau*b
            if float(np.linalg.cond(matrix))>1e10:
                raise ArithmeticError('Unresolved fitted covariance.')
            factor=cho_factor(matrix,lower=True)
            whitened_one=solve_triangular(factor[0],ones,lower=True)
            whitened_y=solve_triangular(factor[0],y,lower=True)
            information=float(whitened_one@whitened_one)
            delta=float(whitened_one@whitened_y/information)
            h=solve_triangular(factor[0].T,whitened_y-delta*whitened_one,lower=False)
            c=vc+tau*bc;cf=cho_factor(c,lower=True);cy=cho_solve(cf,yc)
            trace=float(np.trace(cho_solve(cf,bc)));quadratic=float(cy@bc@cy)
            objective=float(2*np.log(np.diag(cf[0])).sum()+yc@cy+math.log(len(y)))
            score=trace-quadratic
            projection_condition=max(float(np.linalg.cond(c)),float(np.linalg.norm(matrix,2)/np.linalg.eigvalsh(c)[0]))
            score_resolution=256*np.finfo(float).eps*len(y)*projection_condition*(abs(trace)+abs(quadratic))
            return dict(tau=tau,objective=objective,score=score,delta=delta,
                        score_resolution=float(score_resolution),
                        se=math.sqrt(1/information),blup=tau*z.T@h,
                        covariance_condition=float(np.linalg.cond(matrix)))

        try:
            grid=np.linspace(0,bound,129)
            sampled=[evaluate(s) for s in grid]
            candidates=[(float(grid[i]),row) for i,row in enumerate(sampled)]
            for i in range(len(grid)-1):
                if sampled[i]['score']<0<sampled[i+1]['score']:
                    root=brentq(lambda s:evaluate(s)['score'],grid[i],grid[i+1],xtol=1e-300,rtol=1e-14,maxiter=200)
                    candidates.append((float(root),evaluate(root)))
            intervals=[(grid[0],grid[1]),(grid[-2],grid[-1])]
            for i in range(1,len(grid)-1):
                if sampled[i]['objective']<=sampled[i-1]['objective'] and sampled[i]['objective']<=sampled[i+1]['objective']:
                    intervals.append((grid[i-1],grid[i+1]))
            for left,right in intervals:
                solved=minimize_scalar(lambda s:evaluate(s)['objective'],bounds=(left,right),
                                       method='bounded',options={'xatol':1e-11,'maxiter':200})
                if not solved.success or not math.isfinite(solved.x) or not left<=solved.x<=right:
                    return _unknown('reml_search_did_not_converge')
                candidates.append((float(solved.x),evaluate(solved.x)))
            minimum=min(row['objective'] for _,row in candidates)
            tie_band=128*np.finfo(float).eps*max(1,abs(minimum))
            near=[pair for pair in candidates if pair[1]['objective']-minimum<=tie_band]
            def violation(pair):
                s,row=pair
                return max(0,-row['score']) if s==0 else max(0,row['score']) if s==bound else abs(row['score'])
            coordinate,best=min(near,key=violation)
        except (ArithmeticError,np.linalg.LinAlgError,RuntimeError):
            return _unknown('unresolved_reml_search')
        unknown=[]
        objective_band=128*np.finfo(float).eps*max(1,abs(best['objective']),abs(sampled[-1]['objective']))
        upper_gap=sampled[-1]['objective']-best['objective']
        upper_unresolved=bool(upper_gap<=objective_band)
        if upper_unresolved:
            unknown.append('variance_upper_bound_active')
        elif (abs(best['score']) if coordinate>0 else max(0,-best['score']))>best['score_resolution']:
            unknown.append('reml_stationarity_unresolved')
        estimate=location+best['delta'];critical=float(stats.norm.isf(float(item['alpha'])/2))
        interval=[estimate-critical*best['se'],estimate+critical*best['se']]
        if not interval[0]<estimate<interval[1]:
            interval=None;unknown.append('confidence_interval_resolution_lost')
        return dict(meaning='One Gaussian group random-intercept variance estimated by bounded scalar REML with supplied fixed sampling covariance. Normal mean intervals plug in the fitted variance; model adequacy and general multilevel inference are unverified.',
                    model='group_random_intercept_known_sampling_covariance',estimate=estimate,
                    effect_scale=item['effect_scale'],estimate_count=len(values),variance_component_count=1,
                    standard_error=best['se'],confidence_interval=interval,alpha=float(item['alpha']),
                    tau_squared=best['tau'],tau2_search_upper=upper,variance_on_boundary=coordinate==0 or upper_unresolved,
                    upper_boundary_unresolved=upper_unresolved,upper_objective_gap=upper_gap,
                    objective_resolution_band=float(objective_band),
                    restricted_objective=best['objective'],reml_score=best['score'],
                    reml_score_resolution=best['score_resolution'],
                    covariance_condition_number=best['covariance_condition'],
                    study_order=[s['id'] for s in item['studies']],group_count=len(groups),
                    group_effects=[dict(group=g,conditional_blup=float(value)) for g,value in zip(groups,best['blup'])],
                    variance_component_uncertainty_propagated=False,global_optimum_certified=False,
                    assumptions_verified=False,unassessed_checks=unknown)
    return _guarded(calculate)


def _wild_projection(fit, values, np):
    centered=values-float(np.mean(values))
    theta=np.linalg.solve(fit['r'],fit['q'].T@centered)
    projected=fit['z']@theta;residuals=centered-projected
    current=dict(fit,residuals=residuals,residual_norm=float(np.linalg.norm(residuals)),
                 residual_resolution=float(32*np.finfo(float).eps*max(fit['z'].shape)*
                     (np.linalg.norm(centered)+np.linalg.norm(projected))))
    return current,fit['transform']@theta


def wild_cluster_bootstrap(item, stats):
    import numpy as np
    from sra.dependent_checks import _guarded, _unknown, _collapsed, _linear_fit, _cluster_score
    from sra.error_benchmark import fingerprint

    def calculate():
        if any(_collapsed(s) for s in list(zip(*item['x']))+[item['y']]):
            return _unknown('input_values_collapse_in_float64')
        x=np.asarray(item['x'],dtype=float);raw=np.asarray(item['y'],dtype=float)
        y=raw-float(np.mean(raw))
        fit=_linear_fit(x,y,np)
        if fit is None:
            return _unknown('rank_deficient_or_ill_conditioned_design')
        groups=sorted(set(item['clusters']));ids=np.asarray(item['clusters'])
        masks=[ids==g for g in groups];j=item['terms'].index(item['term'])+1
        n,k,g=len(y),fit['z'].shape[1],len(groups)
        correction=g/(g-1)*(n-1)/(n-k);null=float(item['null_value'])

        def statistic(current,numerator=None):
            if current['residual_norm']<=current['residual_resolution']:
                return None
            inverse=np.linalg.solve(current['r'],np.eye(k))
            a=current['transform'][j]@inverse@inverse.T
            influences,errors=[],[]
            for mask in masks:
                score,error,_=_cluster_score(current,mask,'CR1',np)
                influences.append(float(a@score));errors.append(float(np.abs(a)@error))
            se=math.sqrt(correction*sum(v*v for v in influences))
            resolution=math.sqrt(correction*sum(v*v for v in errors))
            if not math.isfinite(se) or se<=resolution:
                return None
            value=(float(current['beta'][j])-null if numerator is None else numerator)/se
            return value if math.isfinite(value) else None

        observed=statistic(fit)
        if observed is None:
            return _unknown('observed_bootstrap_studentization_unresolved')
        adjusted=y-null*(x[:,j-1]-float(np.mean(x[:,j-1])))
        nuisance=np.delete(x,j-1,axis=1)
        if nuisance.shape[1]:
            restricted=_linear_fit(nuisance,adjusted,np)
            if restricted is None:
                return _unknown('restricted_bootstrap_design_unresolved')
            restricted_residual=restricted['residuals']
        else:
            restricted_residual=adjusted-float(np.mean(adjusted))
        distribution=[]
        for signs in itertools.product((-1.,1.),repeat=g):
            weights=np.zeros(n)
            for mask,sign in zip(masks,signs):weights[mask]=sign
            current,change=_wild_projection(fit,restricted_residual*weights,np)
            distribution.append(statistic(current,float(change[j])))
        undefined=sum(t is None for t in distribution)
        band=1e-10*max(1,abs(observed))
        numerator=sum(t is not None and abs(t)>=abs(observed)-band for t in distribution)
        symmetry=max(abs(distribution[i]+distribution[-1-i]) for i in range(len(distribution))) if not undefined else None
        endpoints=max(abs(abs(distribution[i])-abs(observed)) for i in (0,-1)) if not undefined else None
        invariant_unresolved=not undefined and (symmetry>band or endpoints>band or numerator<2)
        unknown=['bootstrap_studentization_unresolved'] if undefined else ['bootstrap_sign_invariance_unresolved'] if invariant_unresolved else []
        return dict(meaning='Null-imposed wild cluster bootstrap-t with complete Rademacher sign enumeration and CR1 studentization. Enumeration is complete, not a finite-sample exact/randomization test or a guarantee of reliable few-cluster inference.',
                    term=item['term'],null_value=item['null_value'],null_imposed=True,
                    observed_t=observed,cluster_count=g,enumerated_sign_vectors=len(distribution),
                    weights='Rademacher_minus_one_plus_one',studentization='CR1',numerical_tie_band=band,
                    p_numerator=numerator if not unknown else None,p_denominator=len(distribution),
                    p_value=numerator/len(distribution) if not unknown else None,
                    maximum_sign_symmetry_error=symmetry,original_replication_error=endpoints,
                    unresolved_replicates=undefined,bootstrap_statistics_sha256=fingerprint({'statistics':distribution}),
                    finite_sample_exact_test=False,randomization_test=False,assumptions_verified=False,
                    unassessed_checks=unknown)
    return _guarded(calculate)


def cluster_power_analysis(item, stats):
    from sra.dependent_checks import _guarded, _unknown

    def calculate():
        m=item['cluster_size'];rho=float(item['icc']);effect=float(item['effect_size']);alpha=float(item['alpha'])
        variance=rho+(1-rho)/m
        def power(k):
            if effect==0:
                return alpha
            df=2*k-2;critical=float(stats.t.isf(alpha/2,df));noncentrality=effect*math.sqrt(k/(2*variance))
            left=float(stats.nct.cdf(-critical,df,noncentrality))
            if not math.isfinite(left) or not 0<=left<=1:
                left=float(stats.nct.sf(critical,df,-noncentrality))
            right=float(stats.nct.sf(critical,df,noncentrality))
            if not math.isfinite(right) or not 0<=right<=1 or not math.isfinite(left) or not 0<=left<=1:
                raise ArithmeticError('Unusable noncentral-t tail.')
            value=right+left
            if not math.isfinite(value) or not 0<value<=1:
                raise ArithmeticError('Unusable noncentral-t probability.')
            return value
        try:
            target=None;previous=None;unknown=[]
            if item['mode']=='calculate':
                k=item['clusters_per_arm'];value=power(k)
            else:
                target=float(item['target_power']);maximum=item['max_clusters_per_arm']
                if target<=alpha:
                    return _unknown('planning_target_collapses_in_float64')
                low,high=2,2
                while high<maximum and power(high)<target:
                    low=high;high=min(maximum,2*high)
                if power(high)<target:
                    k=high;value=power(k);unknown.append('target_unreachable_within_cluster_bound')
                else:
                    while high-low>1:
                        middle=(low+high)//2
                        if power(middle)>=target:high=middle
                        else:low=middle
                    k=2 if power(2)>=target else high;value=power(k)
                    previous=power(k-1) if k>2 else None
                    if previous is not None and previous>=target:
                        unknown.append('integer_search_minimality_unresolved')
                if abs(value-target)<=64*math.ulp(1.) or (previous is not None and abs(previous-target)<=64*math.ulp(1.)):
                    unknown.append('planning_target_at_numerical_resolution')
            if value==1:
                unknown.append('power_saturated_at_float_boundary')
        except ArithmeticError:
            return _unknown('noncentral_t_power_unresolved')
        return dict(meaning='Prospective power for a balanced two-arm pooled t-test of independent Gaussian cluster means, equal cluster sizes and common marginal variance/ICC. No unequal-size/variance, binary, stepped-wedge or general mixed-model planning is implemented.',
                    mode=item['mode'],clusters_per_arm=k,total_clusters=2*k,cluster_size=m,
                    total_participants=2*k*m,inference_df=2*k-2,design_effect=1+(m-1)*rho,
                    cluster_mean_variance_over_individual_variance=variance,effect_size=effect,
                    effect_standardizer='individual_marginal_population_sd',icc=rho,alpha=alpha,
                    power=value if value<1 else None,target_power=target,
                    previous_cluster_count_power=previous,
                    minimal_within_supported_range=item['mode']=='sample_size' and not unknown,
                    assumptions_verified=False,unassessed_checks=unknown)
    return _guarded(calculate)
