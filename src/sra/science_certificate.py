"""Separate scalar interpreter verifies certificates; it does not call the prover."""
import hashlib
import operator

from sra.science_kernel_spec import canonical, digest, parse_json, prepare_science_problem
from sra.science_kernel import report_metadata
from sra.science_interval import BIT_LIMIT


def _bounds(term):
    if term[0] == 'interval':
        return term[1:], None
    left, reason = _bounds(term[1])
    if left is None:
        return None, reason
    right, reason = _bounds(term[2])
    if right is None:
        return None, reason
    if term[0] == 'div' and right[0] <= 0 <= right[1]:
        return None, 'DIVISOR_INCLUDES_ZERO'
    operation = {'add': operator.add, 'sub': operator.sub, 'mul': operator.mul, 'div': operator.truediv}[term[0]]
    corners = [operation(a, b) for a in left for b in right]
    result = min(corners), max(corners)
    if any(max(v.numerator.bit_length(), v.denominator.bit_length()) > BIT_LIMIT for v in result):
        return None, 'ARITHMETIC_RESOURCE_LIMIT'
    return result, None


def _observation(row):
    left, lreason = _bounds(row['left_term'])
    right, rreason = _bounds(row['right_term'])
    value = None
    if left is not None and right is not None:
        if row['relation'] in ('eq', 'ne'):
            overlap = max(left[0], right[0]) <= min(left[1], right[1])
            point = left[0] == left[1] == right[0] == right[1]
            value = True if point else False if not overlap else None
            if value is not None and row['relation'] == 'ne':
                value = not value
        else:
            operation = {'lt': operator.lt, 'le': operator.le, 'ge': operator.ge, 'gt': operator.gt}[row['relation']]
            corners = [operation(a, b) for a in left for b in right]
            value = True if all(corners) else False if not any(corners) else None
    return dict(id=row['id'], atom=row['atom'], relation=row['relation'], value=value,
                left_bounds=None if left is None else [str(v) for v in left],
                right_bounds=None if right is None else [str(v) for v in right],
                reason=lreason or rreason or ('INTERVAL_OVERLAP' if value is None else 'EXACT_INTERVAL_COMPARISON'),
                source_refs=row['source_refs'])


def _truth(term, world):
    op = term[0]
    if op == 'atom':
        return world[term[1]]
    if op == 'const':
        return term[1]
    if op == 'not':
        return not _truth(term[1], world)
    if op == 'and':
        return all(_truth(arg, world) for arg in term[1:])
    if op == 'or':
        return any(_truth(arg, world) for arg in term[1:])
    left, right = _truth(term[1], world), _truth(term[2], world)
    return (not left or right) if op == 'implies' else left == right


def _verify(problem, report):
    arithmetic = [_observation(row) for row in problem['arithmetic']]
    metadata = report_metadata(problem, arithmetic)
    required = set(metadata) | {'basis_state', 'admissible_worlds', 'admissible_worlds_sha256', 'constraint_ids', 'conflict_core', 'claims', 'certificate_sha256'}
    if set(report) != required or any(canonical(report[key]) != canonical(value) for key, value in metadata.items()):
        return False
    if report['certificate_sha256'] != digest({key: value for key, value in report.items() if key != 'certificate_sha256'}):
        return False
    atoms, worlds = problem['atoms'], 1 << len(problem['atoms'])
    universe = (1 << worlds) - 1
    fixed = [row for row in problem['facts'] + arithmetic if row['value'] is not None]
    entries = {row['id']: 0 for row in fixed + problem['rules']}
    claim_masks = {row['id']: 0 for row in problem['claims']}
    for number in range(worlds):
        world = {atom: bool(number & (1 << index)) for index, atom in enumerate(atoms)}
        bit = 1 << number
        for row in fixed:
            if world[row['atom']] is row['value']:
                entries[row['id']] |= bit
        for row in problem['rules']:
            if _truth(row['term'], world):
                entries[row['id']] |= bit
        for row in problem['claims']:
            if _truth(row['term'], world):
                claim_masks[row['id']] |= bit
    def models(keys):
        value = universe
        for key in keys:
            value &= entries[key]
        return value
    def valid_basis(keys, target):
        if not isinstance(keys, list) or any(not isinstance(key, str) or key not in entries for key in keys) or len(set(keys)) != len(keys):
            return False
        return target(models(keys)) and all(not target(models([other for other in keys if other != key])) for key in keys)
    def witness(mask):
        if not mask:
            return None
        number = min(i for i in range(worlds) if mask & (1 << i))
        return dict(world_index=number, assignment={atom: bool(number & (1 << index)) for index, atom in enumerate(atoms)})
    actual = models(entries)
    expected = dict(basis_state='CONSISTENT' if actual else 'INCONSISTENT', admissible_worlds=actual.bit_count(),
                    admissible_worlds_sha256=hashlib.sha256(actual.to_bytes((worlds + 7) // 8, 'little')).hexdigest(),
                    constraint_ids=sorted(entries))
    if any(canonical(report[key]) != canonical(value) for key, value in expected.items()):
        return False
    if actual:
        if report['conflict_core'] != []:
            return False
    elif not valid_basis(report['conflict_core'], lambda value: value == 0):
        return False
    if not isinstance(report['claims'], list) or len(report['claims']) != len(problem['claims']):
        return False
    for row, claim in zip(problem['claims'], report['claims']):
        yes = actual & claim_masks[row['id']]
        no = actual & (universe ^ claim_masks[row['id']])
        if not actual:
            status, reason = 'UNRESOLVED', 'INCONSISTENT_PREMISES'
        elif yes and no:
            status, reason = 'UNRESOLVED', 'BOTH_MODELS_POSSIBLE'
        elif yes:
            status, reason = 'ENTAILED', 'ALL_ADMISSIBLE_MODELS'
        else:
            status, reason = 'CONTRADICTED', 'NO_ADMISSIBLE_SUPPORTING_MODEL'
        expected_claim = dict(id=row['id'], scope=row['scope'], expression=row['expression'], status=status, reason=reason,
                              supporting_models=yes.bit_count(), counter_models=no.bit_count(),
                              supporting_world=witness(yes), counter_world=witness(no))
        if set(claim) != set(expected_claim) | {'basis_ids'} or any(canonical(claim[key]) != canonical(value) for key, value in expected_claim.items()):
            return False
        if status == 'UNRESOLVED':
            if claim['basis_ids'] != []:
                return False
        else:
            forbidden = universe ^ claim_masks[row['id']] if status == 'ENTAILED' else claim_masks[row['id']]
            if not valid_basis(claim['basis_ids'], lambda value: bool(value) and value & forbidden == 0):
                return False
    return True


def verify_science_certificate(spec, certificate):
    problem = prepare_science_problem(spec)
    try:
        report = parse_json(certificate)
        valid = isinstance(report, dict) and _verify(problem, report)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        valid = False
    return dict(schema_version='scientific-proof-verification/1.0', valid=valid,
                reason='CERTIFICATE_RECHECKED' if valid else 'INVALID_CERTIFICATE',
                input_sha256=problem['input_sha256'],
                scope='Independent scalar/endpoint recheck of the finite formal problem; empirical truth and source authenticity are not verified.')
