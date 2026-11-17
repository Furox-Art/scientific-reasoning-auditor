"""Bounded syntax for the independent finite scientific proof kernel."""
import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path

from sra.json_utils import reject_duplicate_keys

MAX_BYTES = 1024 * 1024
ENGINE_VERSION = 'sra-finite-interval-1'
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,63}\Z')
SCOPES = ('declared_problem', 'supplied_corpus', 'supplied_search', 'supplied_measurement_model', 'declared_method')
LIMITATIONS = [
    'Formal entailment concerns supplied statements and bounds, not empirical scientific truth.',
    'Source hashes and exact quotations verify identity, not authenticity or correct semantic interpretation.',
    'Unknown arithmetic predicates remain free Boolean atoms; joint numeric feasibility is not solved.',
    'Interval arithmetic encloses all allowed inputs; repeated intervals do not imply shared-variable dependence.',
    'A deletion-minimal basis/core is not necessarily a minimum-cardinality explanation.',
    'Model counts are not probabilities or scientific confidence; no prior distribution is assumed.',
    'General novelty, literature adequacy, measurement validity and method appropriateness are NOT_ASSESSED.',
]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def kernel_digest():
    root = Path(__file__).parent
    data = b''.join(name.encode() + b'\0' + (root / name).read_bytes() for name in
                    ('science_kernel_spec.py', 'science_interval.py', 'science_kernel.py', 'science_certificate.py'))
    return hashlib.sha256(data).hexdigest()


def parse_json(value):
    def reject(token):
        raise ValueError('Nonstandard JSON constants are forbidden.')
    try:
        raw = value if isinstance(value, str) else canonical(value)
        if len(raw) > MAX_BYTES or len(raw.encode('utf-8')) > MAX_BYTES:
            raise ValueError('Proof input exceeds 1 MiB.')
        return json.loads(raw, object_pairs_hook=reject_duplicate_keys, parse_constant=reject)
    except (RecursionError, TypeError, UnicodeError) as exc:
        raise ValueError('Proof input must be bounded JSON.') from exc


def fields(row, required, optional=()):
    if not isinstance(row, dict) or set(row) - set(required) - set(optional) or set(required) - set(row):
        raise ValueError('Missing or unsupported proof fields.')


def text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError('Proof text is empty or oversized.')
    return value


def rows(value, maximum, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError('Proof record count exceeds its bound.')
    return value


def identifier(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError('Proof identifiers must be simple names of at most 64 characters.')
    return value


def rational(value):
    if type(value) is int:
        result = Fraction(value)
    elif isinstance(value, str) and len(value) <= 64 and re.fullmatch(r'[+-]?(?:[0-9]+/[1-9][0-9]*|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,2})?)', value):
        result = Fraction(value)
    else:
        raise ValueError('Exact numbers require integers or bounded decimal/rational strings; floats are forbidden.')
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 256:
        raise ValueError('Exact numeric literals exceed 256 bits.')
    return result


def expression(value, atoms, budget, numeric=False, depth=0):
    budget[0] += 1
    if budget[0] > 512 or depth > 16:
        raise ValueError('Proof expressions exceed 512 total nodes or depth 16.')
    if numeric and (isinstance(value, str) or type(value) is int):
        number = rational(value)
        return ('interval', number, number)
    if not isinstance(value, dict):
        raise ValueError('Proof expressions require the structured expression language.')
    if numeric and 'interval' in value:
        fields(value, ('interval',))
        bounds = rows(value['interval'], 2, 2)
        low, high = map(rational, bounds)
        if low > high:
            raise ValueError('Interval bounds must be ordered.')
        return ('interval', low, high)
    if not numeric and 'atom' in value:
        fields(value, ('atom',))
        if not isinstance(value['atom'], str) or value['atom'] not in atoms:
            raise ValueError('Undeclared proof atom.')
        return ('atom', value['atom'])
    if not numeric and 'const' in value:
        fields(value, ('const',))
        if type(value['const']) is not bool:
            raise ValueError('Logical constants must be booleans.')
        return ('const', value['const'])
    fields(value, ('op', 'args'))
    op = value['op']
    allowed = ('add', 'sub', 'mul', 'div') if numeric else ('and', 'or', 'not', 'implies', 'iff')
    if not isinstance(op, str) or op not in allowed:
        raise ValueError('Unsupported proof operation.')
    args = rows(value['args'], 16, 1)
    if (numeric or op in ('implies', 'iff')) and len(args) != 2 or op == 'not' and len(args) != 1 or op in ('and', 'or') and len(args) < 2:
        raise ValueError('Proof operation arity is invalid.')
    return (op, *(expression(arg, atoms, budget, numeric, depth + 1) for arg in args))


def prepare_science_problem(value):
    spec = parse_json(value)
    fields(spec, ('schema_version', 'atoms', 'facts', 'arithmetic', 'rules', 'claims'), ('sources',))
    if spec['schema_version'] != '1.0':
        raise ValueError('Scientific proof input schema must be 1.0.')
    atoms = rows(spec['atoms'], 16, 1)
    for atom in atoms:
        identifier(atom)
    if len(set(atoms)) != len(atoms):
        raise ValueError('Proof atoms must be distinct.')
    sources, total = {}, 0
    for source in rows(spec.get('sources', []), 16):
        fields(source, ('id', 'text', 'sha256'))
        identity = identifier(source['id'])
        snapshot = text(source['text'], 100000)
        total += len(snapshot)
        actual = hashlib.sha256(snapshot.encode('utf-8')).hexdigest()
        if identity in sources or source['sha256'] != actual or total > 200000:
            raise ValueError('Duplicate source, mismatched snapshot hash or oversized source corpus.')
        sources[identity] = source
    def refs(value):
        result = []
        for ref in rows(value, 8):
            fields(ref, ('source_id', 'quote', 'start'))
            if not isinstance(ref['source_id'], str) or ref['source_id'] not in sources:
                raise ValueError('Unknown evidence source.')
            quote, start = text(ref['quote'], 2000), ref['start']
            snapshot = sources[ref['source_id']]['text']
            if type(start) is not int or not 0 <= start <= len(snapshot) - len(quote) or snapshot[start:start + len(quote)] != quote:
                raise ValueError('Proof evidence quote/offset does not match its snapshot.')
            result.append(dict(ref, end=start + len(quote)))
        return result
    seen, budget, facts, arithmetic, rules, claims = set(), [0], [], [], [], []
    def common(row):
        identity = identifier(row['id'])
        if identity in seen:
            raise ValueError('Proof record identifiers must be globally distinct.')
        seen.add(identity)
    for row in rows(spec['facts'], 32):
        fields(row, ('id', 'atom', 'value', 'origin'), ('source_refs',))
        common(row)
        if not isinstance(row['atom'], str) or row['atom'] not in atoms or row['value'] is not None and type(row['value']) is not bool or row['origin'] not in ('assumption', 'evidence'):
            raise ValueError('Fact atom, Boolean value or origin is invalid.')
        evidence = refs(row.get('source_refs', []))
        if row['origin'] == 'evidence' and not evidence:
            raise ValueError('Evidence facts require exact source quotations; unanchored premises must be assumptions.')
        facts.append(dict(row, source_refs=evidence))
    for row in rows(spec['arithmetic'], 32):
        fields(row, ('id', 'atom', 'relation', 'left', 'right'), ('source_refs',))
        common(row)
        if not isinstance(row['atom'], str) or row['atom'] not in atoms or row['relation'] not in ('lt', 'le', 'eq', 'ne', 'ge', 'gt'):
            raise ValueError('Arithmetic atom or relation is invalid.')
        arithmetic.append(dict(row, left_term=expression(row['left'], atoms, budget, True),
                               right_term=expression(row['right'], atoms, budget, True), source_refs=refs(row.get('source_refs', []))))
    for row in rows(spec['rules'], 32):
        fields(row, ('id', 'expression'))
        common(row)
        rules.append(dict(row, term=expression(row['expression'], atoms, budget)))
    for row in rows(spec['claims'], 32, 1):
        fields(row, ('id', 'scope', 'expression'))
        common(row)
        if row['scope'] not in SCOPES:
            raise ValueError('Claims require an explicitly bounded scientific scope.')
        claims.append(dict(row, term=expression(row['expression'], atoms, budget)))
    return dict(spec=spec, input_sha256=digest(spec), atoms=sorted(atoms), sources=sources,
                facts=facts, arithmetic=arithmetic, rules=rules, claims=claims)
