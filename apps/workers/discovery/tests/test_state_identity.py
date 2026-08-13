"""Story 2.10: State Identity Engine — route templating, fingerprint
scoring, SAME/VARIANT/NEW classification, and the no-URL-change-SPA
widened-mode fallback. Pure unit tests — no Playwright, no DB.
"""

import logging
import uuid
from unittest.mock import patch

import pytest
from discovery_worker.state_identity import (
    StateIdentityCache,
    compute_fingerprint,
    route_template,
    score,
)


def test_route_template_collapses_numeric_ids() -> None:
    assert route_template("https://app.example.com/claims/1001") == route_template(
        "https://app.example.com/claims/1002"
    )
    assert route_template("https://app.example.com/claims/1001") == (
        "https://app.example.com/claims/{id}"
    )


def test_route_template_collapses_uuid_segments() -> None:
    a = route_template("https://app.example.com/orders/a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    b = route_template("https://app.example.com/orders/11112222-3333-4444-5555-666677778888")
    assert a == b == "https://app.example.com/orders/{id}"


def test_route_template_collapses_hash_routed_segments() -> None:
    a = route_template("https://app.example.com/#!/products/42")
    b = route_template("https://app.example.com/#!/products/99")
    assert a == b


def test_route_template_does_not_collapse_non_id_segments() -> None:
    assert route_template("https://app.example.com/claims/active") == (
        "https://app.example.com/claims/active"
    )


def _fp(
    heading: str,
    actions: list[str],
    fields: list[str] | None = None,
    structure: list[str] | None = None,
):
    return compute_fingerprint(heading, actions, fields or [], structure or ["div", "button"])


def test_worked_example_same_page_different_claim_number() -> None:
    """`/claims/1001` and `/claims/1002` sharing route template, heading and
    action set -> SAME."""
    cache = StateIdentityCache()
    fp1 = _fp("Claim Details", ["Edit", "Submit"])
    cache.register(uuid.uuid4(), "https://app.example.com/claims/1001", fp1)

    result = cache.classify(
        "https://app.example.com/claims/1002", _fp("Claim Details", ["Edit", "Submit"])
    )
    assert result.verdict == "SAME"
    assert result.matched_page_id is not None
    assert result.score_result is not None
    assert result.score_result.composite >= cache.threshold_same


def test_worked_example_draft_vs_pending_is_variant() -> None:
    """Same route template, one state shows Edit/Submit, the other shows
    Approve/Reject -> VARIANT, and both stay independently attributable."""
    cache = StateIdentityCache()
    draft_id = uuid.uuid4()
    cache.register(
        draft_id, "https://app.example.com/claims/1001", _fp("Claim Details", ["Edit", "Submit"])
    )

    result = cache.classify(
        "https://app.example.com/claims/1002",
        _fp("Claim Details", ["Approve", "Reject"]),
    )
    assert result.verdict == "VARIANT"
    assert result.matched_page_id == draft_id
    assert result.ambiguous is True


def test_genuinely_different_page_is_new_even_sharing_a_template() -> None:
    cache = StateIdentityCache()
    cache.register(
        uuid.uuid4(), "https://app.example.com/claims/1001", _fp("Claim Details", ["Edit"])
    )
    result = cache.classify(
        "https://app.example.com/claims/1002",
        _fp("Something Unrelated", ["Delete Account"], structure=["nav", "footer"]),
    )
    assert result.verdict == "NEW"


def test_route_template_hard_filter_short_circuits_without_scoring() -> None:
    """AC 1: no known state shares the candidate's route template -> NEW
    immediately, the expensive weighted comparison never runs."""
    cache = StateIdentityCache()
    cache.register(
        uuid.uuid4(), "https://app.example.com/claims/1001", _fp("Claim Details", ["Edit"])
    )
    with patch("discovery_worker.state_identity.score") as mock_score:
        result = cache.classify(
            "https://app.example.com/settings", _fp("Settings", ["Save"])
        )
    assert result.verdict == "NEW"
    mock_score.assert_not_called()


def test_shadow_dom_only_difference_scores_below_same_threshold() -> None:
    """AC 6: two states differing only inside an open shadow root must not
    score identical — the structural signal has to actually see inside it."""
    base_tokens = ["div", "button[role=tablist]"]
    fp_a = compute_fingerprint("Dashboard", ["Save"], [], base_tokens + ["shadow:button"])
    fp_b = compute_fingerprint(
        "Dashboard", ["Save"], [], base_tokens + ["shadow:input", "shadow:label"]
    )
    result = score(fp_a, fp_b)
    assert result.structure_score < 1.0
    assert result.composite < 1.0


def test_widened_mode_triggers_once_route_templates_stop_discriminating(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A run where every state shares one template still separates two
    materially different states, sets the widened flag, and logs once."""
    cache = StateIdentityCache()
    base_url = "https://app.example.com/#/app"
    # Seed enough same-template states to cross the widening threshold.
    for i in range(6):
        cache.register(uuid.uuid4(), base_url, _fp(f"Screen {i}", [f"action-{i}"]))

    assert cache.widened_mode is True

    with caplog.at_level(logging.WARNING, logger="discovery_worker.state_identity"):
        result = cache.classify(base_url, _fp("Totally different screen", ["Delete everything"]))
    assert result.widened_mode is True
    widened_logs = [r for r in caplog.records if "route_discrimination=none" in r.message]
    assert len(widened_logs) == 1

    # Logging again on a second classify() call must not duplicate the line.
    with caplog.at_level(logging.WARNING, logger="discovery_worker.state_identity"):
        cache.classify(base_url, _fp("Yet another screen", ["Some other action"]))
    widened_logs_after = [r for r in caplog.records if "route_discrimination=none" in r.message]
    assert len(widened_logs_after) == 1


def test_widened_mode_bounds_comparison_set() -> None:
    """Task 3's O(n^2) guard — a widened-mode classify() only compares
    against the most recent bounded window, not every cached state."""
    cache = StateIdentityCache()
    base_url = "https://app.example.com/#/app"
    for i in range(50):
        cache.register(uuid.uuid4(), base_url, _fp(f"Screen {i}", [f"action-{i}"]))
    assert cache.widened_mode is True
    # Should not raise or hang, and should still classify correctly against
    # a bounded window rather than scanning all 50 entries.
    result = cache.classify(base_url, _fp("Screen 49", ["action-49"]))
    assert result.verdict == "SAME"
