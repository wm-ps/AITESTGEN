"""Reviewing the plan before trying it (tests_stage.left_out): duplicates and
scenarios needing a flow exploring never saw are left out up front, with
their reason — never more than a third of the plan."""

from explorer_worker.tests_stage import left_out

PLAN = [
    {"title": "Date of birth cannot be in the future"},
    {"title": "Future Date of birth is refused"},
    {"title": "Demand letter shows supporting details"},
    {"title": "ZIP code refuses letters"},
    {"title": "Last name refuses numbers"},
    {"title": "Phone refuses a number with too few digits"},
]


def test_duplicates_and_never_seen_flows_are_left_out_with_their_reason() -> None:
    out = left_out(
        PLAN,
        [
            {"index": 1, "why": "duplicate", "of": 0},
            {"index": 2, "why": "never_seen", "reason": "no demand letter screen was seen"},
        ],
    )
    assert out == {
        1: "Left out before trying: the same check as “Date of birth cannot be in the future”",
        2: "Left out before trying: it needs something exploring never saw"
        " — no demand letter screen was seen",
    }


def test_a_duplicate_must_point_at_an_earlier_scenario_that_is_kept() -> None:
    assert left_out(PLAN, [{"index": 0, "why": "duplicate", "of": 1}]) == {}  # later one
    assert left_out(PLAN, [{"index": 3, "why": "duplicate", "of": 3}]) == {}  # itself
    assert left_out(PLAN, [{"index": 9, "why": "never_seen"}]) == {}  # no such scenario
    # Both of a pair can't go: the one it duplicates is left out already.
    out = left_out(
        PLAN,
        [{"index": 1, "why": "never_seen"}, {"index": 4, "why": "duplicate", "of": 1}],
    )
    assert list(out) == [1]


def test_a_review_leaving_out_too_much_is_ignored() -> None:
    too_many = [{"index": i, "why": "never_seen"} for i in range(3)]
    assert left_out(PLAN, too_many) == {}  # 3 of 6 is more than a third


def test_a_screen_explorer_cannot_reach_is_given_up_after_three_failures() -> None:
    from explorer_worker.tests_stage import should_give_up

    fell_short = ("dropped", "Couldn't carry it out far enough: the app showed Add photos")
    other_drop = ("dropped", "Still passed with its key step removed")
    assert should_give_up([fell_short] * 3)
    assert not should_give_up([fell_short] * 2 + [other_drop])
    # One scenario already worked there: the screen is reachable, keep trying.
    assert not should_give_up([fell_short] * 5 + [("known_bug", None)])
