"""Source-bound coverage of procedures, never scientific adequacy judgments."""
from sra.criteria_catalog import (APPLICABILITY, EXECUTION_STATES, STUDY_TYPES,
                                 SUPPORT_LEVELS, canonical_hash, criteria_catalog)
from sra.document import SourceIdentityError
from sra.domain_evidence import PROFILES


def _pointer(*parts):
    return '/' + '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in parts)


def _check_key(item):
    if item['kind'] == 'cluster_robust_regression' and item.get('leave_one_cluster_out'):
        return 'cluster_robust_regression:sensitivity'
    if item['kind'] == 'causal_graph' and 'sensitivity_edges' in item:
        return 'causal_graph:sensitivity'
    return (item['kind'] + ':' + item['operation'] if item['kind'] == 'statistical_analysis'
            else item['kind'])


def _matches(key, selectors):
    return key in selectors or key.split(':', 1)[0] in selectors


def _state(status, result):
    if status in ('UNAVAILABLE', 'unavailable'):
        return 'unavailable'
    if status in ('FAILED', 'failed'):
        return 'failed'
    if status in ('not_requested', 'not_applicable'):
        return status
    if status not in ('completed', 'CALCULATED', 'VERIFIED', 'REFUTED', 'CANDIDATES', 'PASS', 'FAIL'):
        return 'partial'
    unresolved = {'NOT_VERIFIED', 'UNDETERMINED', 'UNVERIFIED', 'UNAVAILABLE', 'FAILED'}
    if (result.get('execution_status') == 'partial' or
            result.get('status') in ('NOT_VERIFIED', 'UNDETERMINED', 'UNVERIFIED') or
            (result.get('status') == 'PARTIAL' and result.get('reported_checks') != []) or
            any(check.get('status') in unresolved for check in result.get('reported_checks', ())) or
            result.get('unassessed_checks') or result.get('unknown_domains')):
        return 'partial'
    return 'completed'


def _evidence(row, modules, requested, scientific_kinds):
    refs = []

    def add(name, pointer, *, check_id=None, check_status=None, details=None, scope):
        module = modules[name]
        state = _state(check_status or module['status'],
                       details if details is not None else module.get('result') or {})
        refs.append({'module': name, 'pointer': pointer, 'check_id': check_id,
                     'check_status': check_status, 'module_status': module['status'],
                     'execution_status': state, 'assessment_scope': scope,
                     'source_sha256': module['source_sha256'],
                     'extracted_text_sha256': module['extracted_text_sha256']})

    for name in row['modules']:
        if name in modules:
            add(name, _pointer('modules', name), scope=(
                'supplied_formulas_or_values_only' if name in ('statistics', 'scientific', 'logic')
                else 'text_or_metadata_screening_only'))
    for name, module in modules.items():
        profile = name.removeprefix('discipline:') if name.startswith('discipline:') else None
        if profile in PROFILES and module['result'] is None:
            if set(row['profile_rules']) & {rule.key for rule in PROFILES[profile]['rules']}:
                add(name, _pointer('modules', name), scope='requested_paragraph_screening_only')
        elif profile in PROFILES:
            for index, item in enumerate(module['result'].get('items', [])):
                if item['rule_id'] in row['profile_rules']:
                    add(name, _pointer('modules', name, 'result', 'items', index),
                        check_id=item['rule_id'], scope='paragraph_cues_only')
    toolkit = modules.get('toolkit')
    if toolkit is not None:
        if toolkit['result'] is None:
            if any(_matches(key, row['toolkit_checks']) for key in requested.values()):
                add('toolkit', _pointer('modules', 'toolkit'), scope='requested_structured_inputs_only')
        else:
            for index, item in enumerate(toolkit['result']['checks']):
                if _matches(requested.get(item['id'], item['kind']), row['toolkit_checks']):
                    add('toolkit', _pointer('modules', 'toolkit', 'result', 'checks', index),
                        check_id=item['id'], check_status=item['status'], details=item['details'],
                        scope={'bias_assessment': 'caller_judgments_only',
                               'ml_validation': 'declared_manifest_only',
                               'citation_context': 'lexical_retrieval_only',
                               'citation_match': 'lexical_retrieval_only',
                               'source_overlap': 'lexical_overlap_only',
                               'checklist_evidence': 'caller_checklist_records_only',
                               'figure_svg': 'svg_inventory_only',
                               'publication_status': 'registry_update_snapshot_only'}.get(item['kind'], 'supplied_structured_inputs_only'))
    science = modules.get('scientific')
    if row['scientific_checks'] and science is not None:
        if science['result'] is None:
            if science['status'] != 'not_requested' and set(row['scientific_checks']) & set(scientific_kinds):
                add('scientific', _pointer('modules', 'scientific'), scope='unresolved_scientific_check_selection')
        else:
            for index, item in enumerate(science['result'].get('checks', [])):
                if item['kind'] in row['scientific_checks']:
                    add('scientific', _pointer('modules', 'scientific', 'result', 'checks', index),
                        check_id=item.get('id'), check_status=item['status'], details=item,
                        scope='supplied_scientific_values_only')
    if row['id'] == 'publication_updates' and modules.get('citations', {}).get('result'):
        for index, item in enumerate(modules['citations']['result']['results']):
            if item.get('publication_status'):
                add('citations', _pointer('modules', 'citations', 'result', 'results', index, 'publication_status'),
                    check_id=item['doi'], scope='registry_update_snapshot_only')
    return refs


def _applicability(row, study_type, refs):
    types = row['study_types']
    if types and study_type in ('unknown', 'mixed'):
        return 'requires_review', 'Study type is unknown or mixed; confirm criterion applicability.'
    if types and study_type not in types:
        if any(ref['module'] not in ('reasoning', 'writing', 'citations') and
               ref['execution_status'] not in ('not_requested', 'not_applicable') for ref in refs):
            return 'requires_review', 'Requested checks or selected specialist screening conflict with type-specific applicability; confirm scope.'
        return 'not_applicable', 'Outside the declared study-type scope; this is a caller declaration, not independent classification.'
    if row['conditional']:
        return 'requires_review', 'Applicability depends on methods, subjects or claims that require human confirmation.'
    return 'applicable', 'Included for the declared study type; adequacy still requires human assessment.'


def _execution(row, applicability, refs):
    if applicability == 'not_applicable':
        return 'not_applicable'
    states = {ref['execution_status'] for ref in refs} - {'not_requested', 'not_applicable'}
    if states:
        if states == {'unavailable'}:
            return 'unavailable'
        if states == {'failed'}:
            return 'failed'
        if states != {'completed'}:
            return 'partial'
        structured = {'supplied_formulas_or_values_only', 'supplied_structured_inputs_only',
                      'supplied_scientific_values_only', 'declared_manifest_only'}
        return 'checks_completed' if any(ref['execution_status'] == 'completed' and
                                        ref['assessment_scope'] in structured for ref in refs) else 'screening_completed'
    return {'human_review_only': 'human_review_required', 'not_implemented': 'not_implemented'}.get(
        row['support_level'], 'not_requested')


def build_criteria_matrix(study_type, modules, source_sha256, extracted_text_sha256, toolkit_checks=(), scientific_kinds=()):
    """Derive a matrix from unified-review executions and validated requested checks."""
    if study_type not in STUDY_TYPES:
        raise ValueError('Unsupported declared study type for criteria coverage.')
    for module in modules.values():
        if module['source_sha256'] != source_sha256 or module['extracted_text_sha256'] != extracted_text_sha256:
            raise SourceIdentityError('Criteria evidence has a mismatched source identity.')
    catalog = criteria_catalog()
    requested = {item['id']: _check_key(item) for item in toolkit_checks}
    rows = []
    for definition in catalog['criteria']:
        row = dict(definition)
        refs = _evidence(row, modules, requested, scientific_kinds)
        applicability, reason = _applicability(row, study_type, refs)
        row.update(applicability=applicability, applicability_reason=reason,
                   execution_status=_execution(row, applicability, refs), evidence=refs,
                   scientific_verdict='NOT_ASSESSED', human_review_required=applicability != 'not_applicable')
        rows.append(row)
    result = {'schema_version': 'scientific-criteria-matrix/1.0',
              'catalog_sha256': catalog['catalog_sha256'], 'source_sha256': source_sha256,
              'extracted_text_sha256': extracted_text_sha256, 'declared_study_type': study_type,
              'criteria': rows, 'summary': {'criteria_total': len(rows)},
              'limitations': [catalog['scope'],
                  'Applicability is conditional on caller declarations; not-applicable rows are not independent exclusions.',
                  'Evidence pointers show execution or supplied observations, not satisfaction of a scientific criterion.',
                  'Source hashes do not establish data authenticity or correct prose-to-formula mapping.',
                  'Every scientific verdict remains NOT_ASSESSED, including after successful calculations or model advice.',
                  'Unsupported checks and human judgments remain explicit; no scientific completeness or quality score is produced.']}
    for field, values in (('applicability', APPLICABILITY), ('support_level', SUPPORT_LEVELS),
                          ('execution_status', EXECUTION_STATES)):
        result['summary'][field] = {value: sum(row[field] == value for row in rows) for value in values}
    result['matrix_sha256'] = canonical_hash(result)
    return result


def criteria_markdown(matrix):
    from sra.report import _safe_md
    lines = ['## Scientific criteria coverage', '',
             'This is a coverage worksheet. All scientific verdicts are NOT_ASSESSED.',
             'Completed procedures and text cues do not establish manuscript quality.', '',
             '| Criterion | Applicability | Available support | This run |',
             '| --- | --- | --- | --- |']
    for row in matrix['criteria']:
        lines.append('| ' + ' | '.join(_safe_md(str(row[key])) for key in
                     ('title', 'applicability', 'support_level', 'execution_status')) + ' |')
    for row in matrix['criteria']:
        if row['applicability'] == 'not_applicable':
            continue
        lines.extend(['', '### ' + _safe_md(row['title']), '',
                      '**Required evidence:** ' + _safe_md(' '.join(row['required_evidence'])),
                      '',
                      '**Procedure:** ' + _safe_md(row['procedure']),
                      '',
                      '**Limit:** ' + _safe_md(row['limitation']),
                      '',
                      '**Applicability basis:** ' + _safe_md(row['applicability_reason']), ''])
        for ref in row['evidence']:
            lines.append('- Evidence pointer: ' + _safe_md(ref['pointer']) +
                         '; execution: ' + _safe_md(ref['execution_status']) +
                         '; scope: ' + _safe_md(ref['assessment_scope']))
    lines.extend(['', '**Catalog SHA-256:** ' + matrix['catalog_sha256'],
                  '**Matrix SHA-256:** ' + matrix['matrix_sha256'], ''])
    lines.extend('- ' + _safe_md(limit) for limit in matrix['limitations'])
    return '\n'.join(lines)
