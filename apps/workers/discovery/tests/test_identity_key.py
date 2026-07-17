"""`compute_identity_key` determinism (Story 2.5, AD-13).

Pure-function test, no DB/AI needed — the identity_key must depend only on
the evidence shape, never on anything an AI might name differently between
runs (the function doesn't even take a name as input, so this is structural,
not just tested-for).
"""

import uuid

from discovery_worker.identity_key import compute_identity_key
from domain import Evidence


def _evidence(details: dict) -> Evidence:
    return Evidence(discovery_run_id=uuid.uuid4(), type="page", details=details)


def test_identity_key_stable_regardless_of_evidence_order() -> None:
    ev_a = _evidence({"url": "https://app.example.com/cart"})
    ev_b = _evidence({"url": "https://app.example.com/checkout"})

    key_forward = compute_identity_key([ev_a, ev_b])
    key_reversed = compute_identity_key([ev_b, ev_a])

    assert key_forward == key_reversed


def test_identity_key_differs_for_different_evidence_shapes() -> None:
    ev_a = _evidence({"url": "https://app.example.com/cart"})
    ev_b = _evidence({"url": "https://app.example.com/checkout"})
    ev_c = _evidence({"url": "https://app.example.com/about"})

    assert compute_identity_key([ev_a, ev_b]) != compute_identity_key([ev_a, ev_c])


def test_identity_key_is_deterministic_across_calls() -> None:
    ev_a = _evidence({"url": "https://app.example.com/cart", "method": "GET"})

    assert compute_identity_key([ev_a]) == compute_identity_key([ev_a])
