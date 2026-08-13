"""Direct coverage for this package's own `classify()` — mirrors the
parametrized cases `discovery_worker`'s `test_safety_engine.py` already
covers via its re-export, so this package (the actual owner of the
pattern lists after the Run All Tests extraction) isn't solely tested
through a downstream re-export.
"""

import pytest
from safety_classifier import classify


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


def test_destructive_wins_over_a_coincidental_safe_match_in_the_same_label() -> None:
    # Destructive is checked first — a label matching both lists (not true
    # of the seed lists, but a customized list could do this) must never
    # come out Safe.
    bucket, matched_list = classify("View and Delete")
    assert bucket == "destructive"
    assert matched_list == "destructive"


def test_empty_or_none_label_is_ambiguous_unmatched() -> None:
    assert classify("") == ("ambiguous", None)
    assert classify(None) == ("ambiguous", None)  # type: ignore[arg-type]
