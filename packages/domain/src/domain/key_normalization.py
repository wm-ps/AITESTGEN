"""Shared key normalization (Story 2.15 Task 2, needed early by Stories 2.13/
2.20 which land before 2.15's own `BlockedTask` entity does).

Stories 2.13 (Data Resolver), 2.15 (Blocked Frontier) and 2.20 (Test Data
Pool) all depend on producing byte-identical keys for the same underlying
field — if they drift, a pool entry silently stops satisfying a block and a
user gets asked for data they already supplied. One function, imported
everywhere, is what prevents that (Story 2.20 Dev Notes).

Deliberately dumb (Story 2.15 Dev Notes): lowercase, strip punctuation and
whitespace, no fuzzy or semantic matching. A deterministic key is debuggable
and predictable; a semantic matcher that merges two genuinely different
requirements is worse than one that occasionally splits a single one.
"""

import re

_WORD = re.compile(r"[a-z0-9]+")


def aggregation_key(field_name: str, input_type: str, route_family: str) -> str:
    """(field name, input type, route family) -> one normalized key.
    "Active Policy Number" and "Policy Number (Active)" must produce the
    same key — that's the whole point of the rewrite this function
    implements (Story 2.15 Dev Notes) — so word *order* is deliberately
    ignored: lowercase, extract word tokens, sort them, rejoin."""
    normalized_name = "-".join(sorted(_WORD.findall(field_name.lower())))
    normalized_type = "-".join(sorted(_WORD.findall(input_type.lower())))
    return f"{route_family}:{normalized_type}:{normalized_name}"
