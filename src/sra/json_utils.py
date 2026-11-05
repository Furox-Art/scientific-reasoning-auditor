"""Strict JSON utilities shared by manuscript input and model response paths."""


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key {key!r} is not permitted.")
        result[key] = value
    return result
