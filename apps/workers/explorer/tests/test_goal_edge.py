"""A walk stops on reaching a screen past the goal's stop point or outside
the goal (pursue.edge_reached) — except a mission the user added themselves."""

from explorer_worker.pursue import edge_reached


def test_landing_past_the_stop_ends_the_walk_as_done() -> None:
    assert edge_reached("past_stop", True) and edge_reached("outside", True)
    assert not edge_reached("on_the_way", True)
    assert not edge_reached("inside", True)
    assert not edge_reached(None, True)  # no goal: nothing changes


def test_a_users_own_mission_is_not_stopped_at_the_edge() -> None:
    assert not edge_reached("outside", False)


def test_scenario_walks_know_each_screens_place_by_its_address() -> None:
    import uuid
    from types import SimpleNamespace

    from explorer_worker.tests_stage import goal_fits_by_address

    def screen(pattern: str, fit: str | None) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), url_pattern=pattern, goal_fit=fit)

    screens = [
        screen("//app#/Find", "inside"),
        screen("//app#/Select", "past_stop"),
        screen("//app#/Resume", "outside"),
        screen("//app#/Resume", "inside"),  # two screens, one address: unknown
        screen("//app#/Home", None),  # not judged
    ]
    assert goal_fits_by_address(screens) == {"//app#/Find": "inside", "//app#/Select": "past_stop"}  # type: ignore[arg-type]
