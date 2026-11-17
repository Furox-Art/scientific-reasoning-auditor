"""Conditional record comparisons; never a global scientific adequacy verdict."""
from datetime import date
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, localcontext
import math
import statistics

from sra.method_audit_spec import TARGET_FIELDS


def _compare(left, right, fields):
    return [{'field': field, 'left': left[field], 'right': right[field],
             'comparison': ('unknown' if left[field] is None or right[field] is None else
                            'equal' if left[field]['value'] == right[field]['value'] else 'different')}
            for field in fields]


def _unresolved(rows):
    return [row['field'] + (':ambiguous_quote' if row['comparison'] != 'unknown' else '')
            for row in rows if row['comparison'] == 'unknown' or
            any(value is not None and value.get('selection') == 'ambiguous_first'
                for value in (row['left'], row['right']))]


def novelty_comparison(item, backend):
    comparisons, unknown = [], []
    for source in item['comparators']:
        rows = _compare(item['contribution'], source['features'], item['dimensions'])
        missing = _unresolved(rows)
        unknown.extend(source['id'] + ':' + field for field in missing)
        state = ('unknown' if missing else 'same_declared_features' if
                 all(row['comparison'] == 'equal' for row in rows) else 'different_declared_features')
        comparisons.append(dict(id=source['id'], sha256=source['sha256'], comparison=state, fields=rows))
    required = item.get('required_comparator_ids')
    missing_required = [] if required is None else [key for key in required if key not in {row['id'] for row in comparisons}]
    unknown.extend('required_comparator:' + key for key in missing_required)
    return 'UNDETERMINED' if unknown else 'CANDIDATES', {
        'text_sha256': item['text_sha256'], 'comparisons': comparisons,
        'required_comparator_ids': required, 'missing_required_comparators': missing_required,
        'same_feature_sources': [row['id'] for row in comparisons if row['comparison'] == 'same_declared_features'],
        'unassessed_checks': unknown, 'scientific_novelty': 'NOT_ASSESSED', 'corpus_recall': 'NOT_ASSESSED',
        'meaning': 'Case-sensitive comparison of caller-mapped features in supplied snapshots only. Equal features identify prior-work review candidates; differences do not establish novelty. Source selection, historical priority, mapping semantics and literature completeness are unverified. Quotes use explicit offsets or a unique occurrence; ambiguous unselected quotes abstain.'}


def question_method_alignment(item, backend):
    rows = _compare(item['question'], item['method'], TARGET_FIELDS)
    unknown = _unresolved(rows)
    differences = [row['field'] for row in rows if row['comparison'] == 'different']
    return 'UNDETERMINED' if unknown else 'REFUTED' if differences else 'VERIFIED', {
        'text_sha256': item['text_sha256'], 'fields': rows, 'differences': differences,
        'unassessed_checks': unknown, 'method_appropriateness': 'NOT_ASSESSED',
        'meaning': 'Literal equality of six caller-mapped question/method target fields only. VERIFIED means the supplied strings agree, not that a method identifies the target or answers the research question. Different strings may describe equivalent concepts; equal strings may hide substantive differences. Causal identification, model choice and mapping semantics require review. Ambiguous unselected quote occurrences abstain; explicit offsets remain caller-supplied evidence roles.'}


def literature_search_audit(item, backend):
    unknown, issues, records = [], [], []
    actual_sources = {row['source'] for row in item['searches']}
    missing_sources = [key for key in item['required_sources'] if key not in actual_sources]
    unknown.extend('source:' + key for key in missing_sources)
    for search in item['searches']:
        missing = [key for key, value in search.items() if value is None]
        unknown.extend(search['id'] + ':' + key for key in missing)
        flags, age = [], None
        if search['searched_on'] is not None:
            age = (date.fromisoformat(item['as_of']) - date.fromisoformat(search['searched_on'])).days
            if age < 0:
                flags.append('search_after_declared_snapshot')
            elif age > item['max_age_days']:
                flags.append('older_than_caller_threshold')
        if (search['coverage_start'] is not None and search['coverage_end'] is not None and
                search['coverage_start'] > search['coverage_end']):
            flags.append('reversed_coverage_period')
        issues.extend(search['id'] + ':' + flag for flag in flags)
        records.append(dict(search, age_days=age, missing_fields=missing, issues=flags))
    counts = item['deduplication']
    missing_counts = [key for key, value in counts.items() if value is None]
    unknown.extend('deduplication:' + key for key in missing_counts)
    count_agreement = None
    if not missing_counts:
        count_agreement = counts['records_before'] - counts['duplicates_removed'] == counts['records_after']
        if not count_agreement:
            issues.append('deduplication_count_mismatch')
    coverage = None
    if 'reference_coverage' in item:
        selected = item['reference_coverage']
        retrieved = set(selected['retrieved'])
        absent = [key for key in selected['required'] if key not in retrieved]
        coverage = dict(selected, missing_required=absent,
                        matched_count=len(selected['required']) - len(absent), required_count=len(selected['required']))
        issues.extend('required_reference_not_retrieved:' + key for key in absent)
    return 'UNDETERMINED' if unknown else 'REFUTED' if issues else 'VERIFIED', {
        'as_of': item['as_of'], 'max_age_days': item['max_age_days'],
        'required_sources': item['required_sources'], 'missing_sources': missing_sources,
        'searches': records, 'deduplication': dict(counts, arithmetic_agrees=count_agreement),
        'reference_coverage': coverage,
        'issues': issues, 'unassessed_checks': unknown, 'literature_adequacy': 'NOT_ASSESSED',
        'meaning': 'Audit of supplied search records, caller-selected sources/age threshold and deduplication arithmetic only. VERIFIED is record consistency, not adequate literature coverage or PRISMA-S compliance. Queries were not executed; source choice, query sensitivity, database coverage, screening and authenticity are unverified. Counts from overlapping searches are not assumed additive. Optional reference coverage concerns only caller-selected, case-sensitive record IDs, not overall search recall.'}


def measurement_agreement(item, backend):
    # Preserve caller decimal differences before converting to binary floats.
    # 160 digits cover the validator's bounded 64-character decimal operands.
    context = Context(prec=160, rounding=ROUND_HALF_EVEN, Emin=-999, Emax=999,
                      capitals=1, clamp=0, flags=[], traps=[InvalidOperation, DivisionByZero, Overflow])
    with localcontext(context):
        differences = [float(Decimal(measured) - Decimal(reference)) for reference, measured in
                       zip(item['reference'], item['measured'])]
    mean = math.fsum(differences) / len(differences)
    sd = statistics.stdev(differences)
    limits = [mean - 1.96 * sd, mean + 1.96 * sd]
    unknown = [key for key in ('independent_pairs', 'normal_differences', 'constant_bias_and_variance')
               if item[key] is not True]
    band = item['acceptable_difference']
    agreement, boundary = None, False
    if band is None:
        unknown.append('acceptable_difference')
    if sd == 0:
        unknown.append('zero_observed_dispersion')
    if band is not None:
        bounds = [float(band[key]) for key in ('lower', 'upper')]
        boundary = any(abs(limit - bound) <= 16 * max(math.ulp(limit), math.ulp(bound), math.ulp(sd), math.ulp(mean))
                       for limit, bound in zip(limits, bounds))
        if boundary:
            unknown.append('floating_point_boundary')
        if not unknown:
            agreement = bounds[0] <= limits[0] and limits[1] <= bounds[1]
    confidence = None
    decision = 'UNDETERMINED' if unknown else 'VERIFIED' if agreement else 'REFUTED'
    if 'confidence_level' in item:
        from sra.measurement_uncertainty import normal_agreement_confidence, confidence_decision
        if any(item[key] is not True for key in ('independent_pairs', 'normal_differences', 'constant_bias_and_variance')) or sd == 0:
            confidence = dict(status='UNDETERMINED', reason='assumptions_or_dispersion_unresolved')
        else:
            confidence = normal_agreement_confidence(mean, sd, len(differences), item['confidence_level'])
        if confidence['status'] != 'CALCULATED':
            unknown.append('confidence_region:' + confidence['reason'])
        elif band is not None and not unknown:
            decision = confidence_decision(confidence, bounds)
            if decision == 'UNDETERMINED':
                unknown.append('confidence_region_crosses_or_touches_acceptance_boundary')
        if unknown:
            decision = 'UNDETERMINED'
    return decision, {
        'confidence_region': confidence,
        'decision_basis': 'simultaneous_confidence_bounds' if 'confidence_level' in item else 'estimated_limits',
        'unit': item['unit'], 'n_pairs': len(differences),
        'pairs': [dict(reference=reference, measured=measured, difference=difference) for reference, measured, difference in
                  zip(item['reference'], item['measured'], differences)],
        'mean_difference': mean, 'sample_sd_difference': sd,
        'rmse': math.sqrt(math.fsum(value * value for value in differences) / len(differences)),
        'estimated_limits_of_agreement': {'lower': limits[0], 'upper': limits[1], 'sd_multiplier': 1.96},
        'acceptable_difference': band, 'estimated_limits_within_bounds': agreement,
        'assumptions': {key: item[key] for key in ('independent_pairs', 'normal_differences', 'constant_bias_and_variance')},
        'unassessed_checks': unknown, 'measurement_validity': 'NOT_ASSESSED',
        'meaning': 'Measured minus reference, paired mean +/- 1.96 sample SD: approximate normal Bland-Altman limits, not confidence intervals by themselves. Default VERIFIED means estimated limits fall within caller-selected bounds; when confidence_level is supplied, the entire conservative confidence region must be inside those bounds under caller-declared assumptions; it does not establish population coverage or general measurement validity. No independence, normality, proportional bias, constant variance, reference accuracy, unit equivalence or acceptable threshold is inferred. Repeated observations per subject require a different model; small samples leave substantial estimation uncertainty. Point-estimate endpoints within 16 local floating-point ULPs of a bound abstain. Confidence decisions also use a conservative 1e-10 construction-scale safety margin; this is not a certified numerical error bound.'}
