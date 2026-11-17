"""Exact rational enclosure arithmetic for native kernel observations."""
from fractions import Fraction

BIT_LIMIT = 4096


def interval(term):
    op = term[0]
    if op == 'interval':
        return (term[1], term[2]), None
    left, reason = interval(term[1])
    if left is None:
        return None, reason
    right, reason = interval(term[2])
    if right is None:
        return None, reason
    if op == 'add':
        result = (left[0] + right[0], left[1] + right[1])
    elif op == 'sub':
        result = (left[0] - right[1], left[1] - right[0])
    else:
        if op == 'div' and right[0] <= 0 <= right[1]:
            return None, 'DIVISOR_INCLUDES_ZERO'
        products = [a * b if op == 'mul' else a / b for a in left for b in right]
        result = min(products), max(products)
    if any(max(value.numerator.bit_length(), value.denominator.bit_length()) > BIT_LIMIT for value in result):
        return None, 'ARITHMETIC_RESOURCE_LIMIT'
    return result, None


def relation(left, right, op):
    if op == 'lt':
        return True if left[1] < right[0] else False if left[0] >= right[1] else None
    if op == 'le':
        return True if left[1] <= right[0] else False if left[0] > right[1] else None
    if op in ('ge', 'gt'):
        return relation(right, left, 'le' if op == 'ge' else 'lt')
    disjoint = left[1] < right[0] or right[1] < left[0]
    equal = left[0] == left[1] == right[0] == right[1]
    value = False if disjoint else True if equal else None
    return None if value is None else not value if op == 'ne' else value


def observation(row):
    left, lreason = interval(row['left_term'])
    right, rreason = interval(row['right_term'])
    value = None if left is None or right is None else relation(left, right, row['relation'])
    return dict(id=row['id'], atom=row['atom'], relation=row['relation'], value=value,
                left_bounds=None if left is None else [str(v) for v in left],
                right_bounds=None if right is None else [str(v) for v in right],
                reason=lreason or rreason or ('INTERVAL_OVERLAP' if value is None else 'EXACT_INTERVAL_COMPARISON'),
                source_refs=row['source_refs'])
