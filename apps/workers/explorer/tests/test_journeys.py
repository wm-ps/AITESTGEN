"""Journey scenarios (tests_stage.journeys_from): one whole-flow scenario per
mission that completed a real flow; variants of a covered route are skipped."""

from types import SimpleNamespace

from explorer_worker.tests_stage import MAX_JOURNEYS, journeys_from


def _m(title: str, kind: str, new: int, steps: int, status: str = "done") -> SimpleNamespace:
    return SimpleNamespace(title=title, kind=kind, new_screens=new, steps=steps, status=status)


# FnolTesting's 15 missions (2026-10-21), as they finished.
FNOL = [
    _m("Report and submit a complete claim", "task", 11, 20),
    _m("Verify urgent-help guidance", "branch", 0, 2),
    _m("Verify roadside safety guidance", "branch", 0, 2),
    _m("Find a policy by policy number", "branch", 2, 6),
    _m("Find a policy using personal details", "task", 1, 5),
    _m("Require truthful safety answers", "rule", 0, 4),
    _m("Try “Neither of these is mine” on Policy selection", "branch", 0, 5),
    _m("Try “Pick up where I left off” on Resume claim", "branch", 0, 2),
    _m("Carry on from Choose claim type", "task", 0, 15),
    _m("Try “Property” on Claim type", "branch", 2, 12),
    _m("Try “2024 Ford Mustang” on Vehicle involvement", "branch", 0, 12),
    _m("Try “Just Now” on Claim incident date and time", "branch", 0, 12),
    _m("Try “I was hit while moving” on Claim incident circumstances", "branch", 0, 17),
    _m("Stuck mission", "task", 3, 9, status="blocked"),
]


def test_fnol_gets_one_journey_per_real_flow_most_new_screens_first() -> None:
    assert [m.title for m in journeys_from(FNOL)] == [
        "Report and submit a complete claim",
        "Try “Property” on Claim type",
        "Find a policy by policy number",
        "Find a policy using personal details",
    ]


def test_journeys_are_capped() -> None:
    many = [_m(f"Task {i}", "task", 1, 9) for i in range(MAX_JOURNEYS + 3)]
    assert len(journeys_from(many)) == MAX_JOURNEYS
