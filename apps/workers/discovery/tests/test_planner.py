"""Story 2.11: action tiering, the specialist decision chain, and the
State Return ladder. Pure unit tests — the ladder is exercised against a
fake page object, no Playwright/DB needed for these.
"""

import pytest
from discovery_worker.planner import (
    TIER_IN_PAGE,
    TIER_NAVIGATION,
    ActionCandidate,
    ExecutionDecision,
    SpecialistVerdict,
    classify_tier,
    decide,
    return_to_state,
)
from discovery_worker.state_identity import StateFingerprint, compute_fingerprint

# --- tiering (AC 1) --------------------------------------------------------


def test_tab_role_is_always_tier_1() -> None:
    candidate = ActionCandidate(
        label="Second",
        role="tab",
        in_landmark=True,  # even inside a nav landmark, role=tab wins
        source_route_template="https://app.example.com/",
    )
    assert classify_tier(candidate) == TIER_IN_PAGE


def test_landmark_position_is_tier_2() -> None:
    candidate = ActionCandidate(
        label="Settings",
        role=None,
        in_landmark=True,
        source_route_template="https://app.example.com/",
    )
    assert classify_tier(candidate) == TIER_NAVIGATION


def test_route_changing_href_is_tier_2() -> None:
    candidate = ActionCandidate(
        label="View order",
        role=None,
        in_landmark=False,
        source_route_template="https://app.example.com/orders",
        target_route_template="https://app.example.com/orders/{id}",
    )
    assert classify_tier(candidate) == TIER_NAVIGATION


def test_same_page_anchor_is_tier_1() -> None:
    candidate = ActionCandidate(
        label="Add to cart",
        role=None,
        in_landmark=False,
        source_route_template="https://app.example.com/product/{id}",
        target_route_template="https://app.example.com/product/{id}",
    )
    assert classify_tier(candidate) == TIER_IN_PAGE


def test_no_href_and_no_landmark_is_tier_1() -> None:
    candidate = ActionCandidate(
        label="Expand details",
        role=None,
        in_landmark=False,
        source_route_template="https://app.example.com/",
    )
    assert classify_tier(candidate) == TIER_IN_PAGE


# --- specialist chain (AC 3/7) ----------------------------------------------


def _candidate() -> ActionCandidate:
    return ActionCandidate(
        label="Delete",
        role=None,
        in_landmark=False,
        source_route_template="https://app.example.com/",
    )


def test_no_opinion_from_any_specialist_defaults_to_execute() -> None:
    result = decide(_candidate())
    assert result == ExecutionDecision("EXECUTE", "default", "no specialist objected")


def test_loop_guard_opinion_wins_and_is_traceable() -> None:
    result = decide(
        _candidate(),
        loop_guard=lambda c: SpecialistVerdict("SKIP", "already done this run"),
    )
    assert result.action == "SKIP"
    assert result.deciding_specialist == "loop_guard"


def test_safety_is_asked_before_data_resolver() -> None:
    """AD-19: safety runs before data resolution — resolving inputs for an
    action that will never execute is wasted work. Both specialists here
    have an opinion; safety's must win since it's asked first."""
    result = decide(
        _candidate(),
        safety=lambda c: SpecialistVerdict("DEFER", "destructive verb"),
        data_resolver=lambda c: SpecialistVerdict("DEFER", "missing required field"),
    )
    assert result.deciding_specialist == "safety"
    assert result.reason == "destructive verb"


def test_data_resolver_only_consulted_when_loop_guard_and_safety_pass() -> None:
    result = decide(
        _candidate(),
        data_resolver=lambda c: SpecialistVerdict("DEFER", "no test data available"),
    )
    assert result.action == "DEFER"
    assert result.deciding_specialist == "data_resolver"


# --- State Return ladder (AC 5/6) ------------------------------------------


class _FakePage:
    """A minimal Playwright-Page stand-in: `_state` is whatever
    `capture_state_signals` should currently report; `go_back`/`goto`
    mutate it deterministically for the test to assert against."""

    def __init__(self, states_by_url: dict[str, str], back_target: str | None = None) -> None:
        self.states_by_url = states_by_url
        self.back_target = back_target
        self.url: str | None = None
        self.goto_calls: list[str] = []
        self.back_calls = 0

    async def goto(self, url: str) -> None:
        self.goto_calls.append(url)
        self.url = url

    async def go_back(self) -> None:
        self.back_calls += 1
        if self.back_target is not None:
            self.url = self.back_target


async def _settle() -> None:
    return None


def _fp_for(heading: str) -> StateFingerprint:
    return compute_fingerprint(heading, [], [], ["div", "button"])


async def _capture_from(page: _FakePage) -> tuple[str, list[str]]:
    heading = page.states_by_url.get(page.url or "", "unknown")
    return heading, ["div", "button"]


@pytest.mark.asyncio
async def test_rung_1_no_op_when_state_already_matches() -> None:
    page = _FakePage(states_by_url={})
    page.url = "irrelevant"
    result = await return_to_state(
        page,
        _fp_for("Dashboard"),
        target_url="https://app.example.com/",
        capture_state_signals=lambda p: _capture_from_matching(),
        settle=_settle,
    )
    assert result.succeeded
    assert result.rung == "no_op"
    assert result.attempts_used == 0
    assert page.goto_calls == []
    assert page.back_calls == 0


async def _capture_from_matching() -> tuple[str, list[str]]:
    return "Dashboard", ["div", "button"]


@pytest.mark.asyncio
async def test_rung_2_browser_back_succeeds_when_it_lands_on_the_right_state() -> None:
    page = _FakePage(
        states_by_url={
            "https://app.example.com/": "Dashboard",
            "https://app.example.com/detail": "Detail",
        },
        back_target="https://app.example.com/",
    )
    page.url = "https://app.example.com/detail"
    result = await return_to_state(
        page,
        _fp_for("Dashboard"),
        target_url="https://app.example.com/",
        capture_state_signals=_capture_from,
        settle=_settle,
    )
    assert result.succeeded
    assert result.rung == "browser_back"
    assert result.attempts_used == 1
    assert page.back_calls == 1
    assert page.goto_calls == []


@pytest.mark.asyncio
async def test_rung_3_renavigate_succeeds_when_back_lands_elsewhere() -> None:
    page = _FakePage(
        states_by_url={
            "https://app.example.com/": "Dashboard",
            "https://app.example.com/detail": "Detail",
        },
        back_target="https://app.example.com/somewhere-else",
    )
    page.states_by_url["https://app.example.com/somewhere-else"] = "Somewhere Else"
    page.url = "https://app.example.com/detail"
    result = await return_to_state(
        page,
        _fp_for("Dashboard"),
        target_url="https://app.example.com/",
        capture_state_signals=_capture_from,
        settle=_settle,
    )
    assert result.succeeded
    assert result.rung == "renavigate"
    assert result.attempts_used == 2
    assert page.goto_calls == ["https://app.example.com/"]


@pytest.mark.asyncio
async def test_rung_4_path_replay_succeeds_via_entry_url() -> None:
    """The target URL alone doesn't reconstruct the state (a form-posted
    page with no deep link) — re-visiting the entry point first does."""

    async def capture(p: _FakePage) -> tuple[str, list[str]]:
        # The direct re-navigate (rung 3) lands on a stale/broken render;
        # only after visiting the entry point does the target URL work.
        if p.goto_calls[-2:] == ["https://app.example.com/", "https://app.example.com/wizard/step2"]:
            return "Step 2", ["div", "button"]
        return "Broken", ["div"]

    page = _FakePage(states_by_url={}, back_target="https://app.example.com/somewhere-else")
    page.url = "https://app.example.com/wizard/step2"
    result = await return_to_state(
        page,
        _fp_for("Step 2"),
        target_url="https://app.example.com/wizard/step2",
        capture_state_signals=capture,
        settle=_settle,
        entry_url="https://app.example.com/",
    )
    assert result.succeeded
    assert result.rung == "path_replay"
    assert result.attempts_used == 3
    assert page.goto_calls[-2:] == ["https://app.example.com/", "https://app.example.com/wizard/step2"]


@pytest.mark.asyncio
async def test_rung_5_gives_up_when_nothing_reconstructs_the_state() -> None:
    page = _FakePage(states_by_url={}, back_target="https://app.example.com/nowhere")
    page.url = "https://app.example.com/wizard/step2"
    result = await return_to_state(
        page,
        _fp_for("Step 2"),
        target_url="https://app.example.com/wizard/step2",
        capture_state_signals=lambda p: _capture_never_matches(),
        settle=_settle,
        entry_url="https://app.example.com/",
    )
    assert not result.succeeded
    assert result.rung == "gave_up"
    assert result.attempts_used == 3


async def _capture_never_matches() -> tuple[str, list[str]]:
    return "Never Matches", ["span"]


@pytest.mark.asyncio
async def test_return_budget_is_respected() -> None:
    """A pathological state abandons after the configured budget, even
    though rung 4 (path_replay) would theoretically still be available."""
    page = _FakePage(states_by_url={}, back_target="https://app.example.com/nowhere")
    page.url = "https://app.example.com/wizard/step2"
    result = await return_to_state(
        page,
        _fp_for("Step 2"),
        target_url="https://app.example.com/wizard/step2",
        capture_state_signals=lambda p: _capture_never_matches(),
        settle=_settle,
        entry_url="https://app.example.com/",
        return_budget=2,
    )
    assert not result.succeeded
    assert result.attempts_used == 2
