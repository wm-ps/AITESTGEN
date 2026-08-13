"""Story 2.19: loop-prevention consolidation — action history, transition-
cycle detection, route-family bounding and the final action ceiling. Pure
unit tests against `LoopGuardState`, no Playwright/DB needed.
"""

from discovery_worker.planner import ActionCandidate, LoopGuardState


def _candidate(
    label: str, state_key: str, route: str = "https://app.example.com/", in_landmark: bool = False
) -> ActionCandidate:
    return ActionCandidate(
        label=label,
        role=None,
        in_landmark=in_landmark,
        source_route_template=route,
        state_key=state_key,
    )


# --- AC 2a: action history ---------------------------------------------------


def test_repeated_action_from_same_state_is_skipped() -> None:
    guard = LoopGuardState()
    candidate = _candidate("Delete", state_key="https://app.example.com/orders/1")
    assert guard.guard(candidate).decision is None
    guard.record_executed(candidate)

    verdict = guard.guard(candidate)
    assert verdict.decision == "SKIP"
    assert "action_history" in verdict.reason


def test_same_label_from_a_different_state_is_not_skipped() -> None:
    guard = LoopGuardState()
    first = _candidate("Delete", state_key="https://app.example.com/orders/1")
    guard.guard(first)
    guard.record_executed(first)

    second = _candidate("Delete", state_key="https://app.example.com/orders/2")
    assert guard.guard(second).decision is None


def test_same_label_in_body_and_chrome_are_independent() -> None:
    """A page-body control and a nav/header/footer control can legitimately
    share an identical accessible name (e.g. a per-row grid "..." action menu
    and a header hamburger both reporting `aria-label="Menu"`) without being
    the same action — executing one must not shadow the other."""
    guard = LoopGuardState()
    body_menu = _candidate("Menu", state_key="https://app.example.com/list", in_landmark=False)
    chrome_menu = _candidate("Menu", state_key="https://app.example.com/list", in_landmark=True)

    assert guard.guard(body_menu).decision is None
    guard.record_executed(body_menu)

    assert guard.guard(chrome_menu).decision is None


# --- AC 2b: transition-cycle detection --------------------------------------


def test_a_b_a_b_oscillation_is_detected() -> None:
    guard = LoopGuardState()
    guard.record_transition("A", "B", "Toggle")
    guard.record_transition("B", "A", "Toggle")
    guard.record_transition("A", "B", "Toggle")
    guard.record_transition("B", "A", "Toggle")

    verdict = guard.guard(_candidate("Anything", state_key="A"))
    assert verdict.decision == "SKIP"
    assert "transition_cycle" in verdict.reason


def test_a_hub_page_revisited_from_several_flows_is_not_falsely_flagged() -> None:
    guard = LoopGuardState()
    for source in ("X", "Y", "Z"):
        guard.record_transition(source, "Hub", f"Open {source}")
        guard.record_transition("Hub", source, f"Open {source}")

    verdict = guard.guard(_candidate("Anything", state_key="Hub"))
    assert verdict.decision is None


def test_different_sibling_links_bouncing_through_the_same_hub_is_not_a_cycle() -> None:
    """The actual production bug: a hub page with a persistent sidebar where
    exploring each distinct sibling link necessarily round-trips through the
    same two URLs (hub <-> the one leaf reached so far). Same two URLs, two
    different actions — not a cycle."""
    guard = LoopGuardState()
    guard.record_transition("Hub", "Leaf", "Master Characteristics")
    guard.record_transition("Leaf", "Hub", "Master Characteristics")
    guard.record_transition("Leaf", "Hub", "Home")
    guard.record_transition("Hub", "Leaf", "Home")

    verdict = guard.guard(_candidate("Specifications", state_key="Leaf"))
    assert verdict.decision is None


# --- AC 2c: route normalization ----------------------------------------------


def test_route_family_cap_bounds_a_parameterized_duplicate() -> None:
    guard = LoopGuardState(route_family_cap=2)
    route = "https://app.example.com/product/{id}"
    for i in range(2):
        candidate = _candidate(
            "Add to cart", state_key=f"https://app.example.com/product/{i}", route=route
        )
        assert guard.guard(candidate).decision is None
        guard.record_executed(candidate)

    third = _candidate("Add to cart", state_key="https://app.example.com/product/999", route=route)
    verdict = guard.guard(third)
    assert verdict.decision == "SKIP"
    assert "route_normalization" in verdict.reason


# --- AC 2f: depth/action ceiling ---------------------------------------------


def test_action_ceiling_is_a_final_backstop() -> None:
    guard = LoopGuardState(action_ceiling=3)
    for i in range(3):
        verdict = guard.guard(_candidate(f"Action {i}", state_key=f"state-{i}"))
        assert verdict.decision is None

    verdict = guard.guard(_candidate("One too many", state_key="state-final"))
    assert verdict.decision == "SKIP"
    assert "ceiling" in verdict.reason


# --- AC 4: every skip is traceable via deciding_specialist/reason ------------


def test_guard_fire_is_traceable_through_decide() -> None:
    from discovery_worker.planner import decide

    guard = LoopGuardState()
    candidate = _candidate("Delete", state_key="https://app.example.com/orders/1")
    guard.record_executed(candidate)

    result = decide(candidate, loop_guard=guard.guard)
    assert result.action == "SKIP"
    assert result.deciding_specialist == "loop_guard"
    assert "action_history" in result.reason
