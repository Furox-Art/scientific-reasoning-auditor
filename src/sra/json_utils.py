"""Strict JSON utilities shared by manuscript input and model response paths."""
import json
from decimal import Decimal


def canonical_json(value, depth=0):
    """Sorted compact JSON, preserving Decimal numeric tokens and their precision."""
    if depth > 64:
        raise ValueError('Canonical JSON exceeds 64 nesting levels.')
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('Canonical JSON requires string object keys.')
        return '{'+','.join(json.dumps(key, ensure_ascii=False)+':'+canonical_json(value[key], depth+1) for key in sorted(value))+'}'
    if isinstance(value, list):
        return '['+','.join(canonical_json(item, depth+1) for item in value)+']'
    if isinstance(value, Decimal) or type(value) in (int, float):
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError('Canonical JSON numbers must be finite.')
        return str(number)
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key {key!r} is not permitted.")
        result[key] = value
    return result
