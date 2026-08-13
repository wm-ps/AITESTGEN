"""Story 2.12: verb/pattern classification, posture-driven resolution of
Ambiguous actions, and the AI-consult fallback guarantee. Pure unit tests —
no Playwright/DB needed.
"""

import pytest
from discovery_worker.planner import ActionCandidate, decide
from discovery_worker.safety_engine import (
    SafetyState,
    classify,
    consult_ai,
    evaluate,
)

# --- AC 1: classification ----------------------------------------------------


@pytest.mark.parametrize(
    "label,expected_bucket,expected_list",
    [
        ("Delete", "destructive", "destructive"),
        ("Remove item", "destructive", "destructive"),
        ("Terminate session", "destructive", "destructive"),
        ("Transfer funds", "destructive", "destructive"),
        ("Make Payment", "destructive", "destructive"),
        ("View details", "safe", "safe"),
        ("Open", "safe", "safe"),
        ("Expand row", "safe", "safe"),
        ("Search", "safe", "safe"),
        ("Filter results", "safe", "safe"),
        ("Submit", "ambiguous", "ambiguous"),
        ("Approve claim", "ambiguous", "ambiguous"),
        ("Save changes", "ambiguous", "ambiguous"),
        ("Frobnicate the widget", "ambiguous", None),
    ],
)
def test_classify_matches_seeded_lists(label, expected_bucket, expected_list) -> None:
    bucket, matched_list = classify(label)
    assert bucket == expected_bucket
    assert matched_list == expected_list


def test_unmatched_label_is_never_classified_safe() -> None:
    bucket, _ = classify("Frobnicate the widget")
    assert bucket != "safe"


# --- AC 2/4: posture-driven verdict ------------------------------------------


def test_destructive_action_is_never_executed_under_either_posture() -> None:
    for posture in ("non_production", "production"):
        verdict = evaluate("Delete", posture)
        assert verdict.verdict == "DESTRUCTIVE"


def test_ambiguous_action_executes_under_non_production() -> None:
    verdict = evaluate("Submit", "non_production")
    assert verdict.verdict == "SAFE"


def test_ambiguous_action_defers_under_production() -> None:
    verdict = evaluate("Submit", "production")
    assert verdict.verdict == "DEFER"


def test_unmatched_action_follows_the_same_posture_rule_as_ambiguous() -> None:
    assert evaluate("Frobnicate", "non_production").verdict == "SAFE"
    assert evaluate("Frobnicate", "production").verdict == "DEFER"


def test_safe_action_executes_regardless_of_posture() -> None:
    assert evaluate("View", "non_production").verdict == "SAFE"
    assert evaluate("View", "production").verdict == "SAFE"


# --- AC 3: AI consultation never overrides the verdict -----------------------


class _RaisingAIProvider:
    async def classify_action_safety(self, label: str, page_context: str) -> str:
        raise TimeoutError("provider timed out")


class _OpinionatedAIProvider:
    async def classify_action_safety(self, label: str, page_context: str) -> str:
        return "DESTRUCTIVE: looks scary"


async def test_ai_timeout_falls_back_to_posture_not_execute() -> None:
    opinion = await consult_ai(_RaisingAIProvider(), "Frobnicate", "some page")
    assert opinion is None
    # The verdict was never waiting on the AI call to begin with.
    verdict = evaluate("Frobnicate", "production")
    assert verdict.verdict == "DEFER"


async def test_ai_opinion_never_overrides_the_posture_driven_verdict() -> None:
    opinion = await consult_ai(_OpinionatedAIProvider(), "Frobnicate", "some page")
    assert opinion == "DESTRUCTIVE: looks scary"
    # Even though the AI claims DESTRUCTIVE, evaluate() alone owns the verdict.
    verdict = evaluate("Frobnicate", "non_production")
    assert verdict.verdict == "SAFE"


# --- AC 4: exactly SAFE|DESTRUCTIVE|DEFER, wired through decide() -----------


def _candidate(label: str) -> ActionCandidate:
    return ActionCandidate(
        label=label, role=None, in_landmark=False, source_route_template="/orders/{id}"
    )


def test_destructive_verdict_short_circuits_to_skip_via_decide() -> None:
    safety = SafetyState(posture="non_production")
    result = decide(_candidate("Delete"), safety=safety)
    assert result.action == "SKIP"
    assert result.deciding_specialist == "safety"
    assert safety.last_verdict is not None
    assert safety.last_verdict.verdict == "DESTRUCTIVE"
    assert safety.last_verdict.matched_list == "destructive"


def test_production_posture_defers_ambiguous_via_decide() -> None:
    safety = SafetyState(posture="production")
    result = decide(_candidate("Submit"), safety=safety)
    assert result.action == "DEFER"
    assert result.deciding_specialist == "safety"


def test_safe_verdict_falls_through_to_execute_via_decide() -> None:
    safety = SafetyState(posture="production")
    result = decide(_candidate("View"), safety=safety)
    assert result.action == "EXECUTE"
    assert safety.last_verdict is not None
    assert safety.last_verdict.verdict == "SAFE"
    assert safety.last_verdict.matched_list == "safe"
