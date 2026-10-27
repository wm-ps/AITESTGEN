"""Follow-up missions (missions.follow_ups): ways forward a mission saw on a
screen the Mission Board was planned without get their own mission."""

from explorer_worker.missions import follow_ups
from explorer_worker.pursue import Pursuit

PLANNED_FROM = {"Claims support", "Claim safety check", "Claim policy lookup"}


def _fnol_walk() -> Pursuit:
    # FNOL: policy number → Resume claim report (Start over) → Claim type, done.
    return Pursuit(
        ended="done",
        history=[
            "Claim policy lookup: Policy number = POL-10001 -> Find my policy",
            "Resume claim report: no input -> Start over instead",
        ],
        branches=[
            {
                "step": "Claim safety check",
                "question": "Was anyone hurt?",
                "options_worth_trying_later": ["Someone has minor injuries"],
            },
            {
                "step": "Resume claim report",
                "question": "Resume the unfinished report or start over",
                "options_worth_trying_later": ["Pick up where I left off"],
            },
        ],
    )


def test_untried_choice_and_last_step_become_follow_ups() -> None:
    taken: set[str] = set()
    out = follow_ups("Find a policy", _fnol_walk(), "Claim type", "wizard", PLANNED_FROM, taken)
    assert [m["title"] for m in out] == [
        "Try “Pick up where I left off” on Resume claim report",
        "Carry on from Claim type",
    ]
    # Walks in the way the parent did, up to (not past) the branch screen.
    assert "POL-10001" in out[0]["instructions"]
    assert "Start over" not in out[0]["instructions"]
    assert out[0]["start_screen"] == "Resume claim report"


def test_no_repeats_and_nothing_after_a_stop() -> None:
    taken = {"Try “Pick up where I left off” on Resume claim report", "Carry on from Claim type"}
    assert follow_ups("x", _fnol_walk(), "Claim type", "wizard", PLANNED_FROM, taken) == []
    stopped = _fnol_walk()
    stopped.ended, stopped.branches = "final", []  # stopped before a press that needs your OK
    assert follow_ups("x", stopped, "Claim type", "wizard", PLANNED_FROM, set()) == []
