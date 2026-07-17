"""Deterministic Journey `identity_key` computation (Story 2.5, AD-13).

Computed from the Journey's underlying evidence shape — never from its
AI-generated `name`, which can vary slightly run to run. Story 3.5's
re-discovery dedup later compares against this exact key, so its
construction must be stable now.
"""

import hashlib
import json

from domain import Evidence


def compute_identity_key(supporting_evidence: list[Evidence]) -> str:
    signatures = sorted(json.dumps(row.details, sort_keys=True) for row in supporting_evidence)
    combined = "|".join(signatures)
    return hashlib.sha256(combined.encode()).hexdigest()
