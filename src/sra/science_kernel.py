"""Independent bit-parallel finite-model prover. No SMT, LLM or floating point."""
import hashlib
import json

from sra.science_kernel_spec import MAX_BYTES, ENGINE_VERSION, LIMITATIONS, digest, kernel_digest, prepare_science_problem
from sra.science_interval import observation


def _intersect(entries, universe):
    mask = universe
    for _, value in entries:
        mask &= value
    return mask


def _reduce(entries, universe, target):
    selected = list(entries)
    for identity, _ in entries:
        trial = [entry for entry in selected if entry[0] != identity]
        if target(_intersect(trial, universe)):
            selected = trial
    return [identity for identity, _ in selected]


def _mask(term, variables, universe, cache):
    if term in cache:
        return cache[term]
    op = term[0]
    if op == 'atom':
        value = variables[term[1]]
    elif op == 'const':
        value = universe if term[1] else 0
    else:
        args = [_mask(child, variables, universe, cache) for child in term[1:]]
        if op == 'not':
            value = universe ^ args[0]
        elif op == 'and':
            value = _intersect(list(enumerate(args)), universe)
        elif op == 'or':
            value = 0
            for arg in args:
                value |= arg
        elif op == 'implies':
            value = (universe ^ args[0]) | args[1]
        else:
            value = universe ^ (args[0] ^ args[1])
    cache[term] = value
    return value


def _witness(mask, atoms):
    if not mask:
        return None
    world = (mask & -mask).bit_length() - 1
    return dict(world_index=world, assignment={atom: bool(world & (1 << index)) for index, atom in enumerate(atoms)})


def mask_digest(mask, world_count):
    return hashlib.sha256(mask.to_bytes((world_count + 7) // 8, 'little')).hexdigest()


def report_metadata(problem, arithmetic):
    return dict(schema_version='scientific-proof/1.0', engine_version=ENGINE_VERSION,
                kernel_sha256=kernel_digest(), input_sha256=problem['input_sha256'],
                atom_order=problem['atoms'], universe_worlds=1 << len(problem['atoms']),
                premises=problem['facts'], rules=[dict(id=row['id'], expression=row['expression']) for row in problem['rules']],
                arithmetic=arithmetic,
                sources=[dict(id=key, sha256=row['sha256']) for key, row in sorted(problem['sources'].items())],
                scientific_assessment=dict(novelty='NOT_ASSESSED', literature_adequacy='NOT_ASSESSED',
                                           measurement_validity='NOT_ASSESSED', method_appropriateness='NOT_ASSESSED'),
                limitations=LIMITATIONS.copy())


def prove_science(spec):
    problem = prepare_science_problem(spec)
    atoms = problem['atoms']
    worlds = 1 << len(atoms)
    universe = (1 << worlds) - 1
    variables = {}
    for index, atom in enumerate(atoms):
        block = 1 << index
        variables[atom] = (universe // ((1 << (2 * block)) - 1)) * (((1 << block) - 1) << block)
    arithmetic = [observation(row) for row in problem['arithmetic']]
    entries = [(row['id'], variables[row['atom']] if row['value'] else universe ^ variables[row['atom']])
               for row in problem['facts'] + arithmetic if row['value'] is not None]
    cache = {}
    entries.extend((row['id'], _mask(row['term'], variables, universe, cache)) for row in problem['rules'])
    entries.sort()
    models = _intersect(entries, universe)
    claims = []
    for row in problem['claims']:
        expression = _mask(row['term'], variables, universe, cache)
        supporting, counter = models & expression, models & (universe ^ expression)
        if not models:
            status, reason, basis = 'UNRESOLVED', 'INCONSISTENT_PREMISES', []
        elif not counter:
            status, reason = 'ENTAILED', 'ALL_ADMISSIBLE_MODELS'
            basis = _reduce(entries, universe, lambda mask: bool(mask) and not mask & (universe ^ expression))
        elif not supporting:
            status, reason = 'CONTRADICTED', 'NO_ADMISSIBLE_SUPPORTING_MODEL'
            basis = _reduce(entries, universe, lambda mask: bool(mask) and not mask & expression)
        else:
            status, reason, basis = 'UNRESOLVED', 'BOTH_MODELS_POSSIBLE', []
        claims.append(dict(id=row['id'], scope=row['scope'], expression=row['expression'], status=status, reason=reason,
                           basis_ids=basis, supporting_models=supporting.bit_count(), counter_models=counter.bit_count(),
                           supporting_world=_witness(supporting, atoms), counter_world=_witness(counter, atoms)))
    report = report_metadata(problem, arithmetic)
    report.update(basis_state='CONSISTENT' if models else 'INCONSISTENT', admissible_worlds=models.bit_count(),
                  admissible_worlds_sha256=mask_digest(models, worlds), constraint_ids=[key for key, _ in entries],
                  conflict_core=[] if models else _reduce(entries, universe, lambda mask: not mask), claims=claims)
    report['certificate_sha256'] = digest(report)
    if len(json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8')) > MAX_BYTES:
        raise ValueError('Complete proof certificate exceeds 1 MiB; no partial certificate is returned.')
    return report
