"""agent.run_exploration's LangGraph loop — a fake MCP client (scripted
snapshots) and a fake AIProvider (scripted decisions), no real subprocess or
LLM call. Confirms the loop stops on goal_satisfied, stops on the turn cap,
records a heartbeat per turn, and resolves locator candidates from the
snapshot the decision's `ref` actually came from."""

import pytest
from ai_provider.live_exploration_decision import LiveExplorationDecision
from generation_worker.live_exploration.agent import run_exploration

pytestmark = pytest.mark.asyncio

_SNAPSHOT = (
    '- generic [ref=e1]:\n'
    '  - Page URL: https://app.example.com/tenants\n'
    '  - button "Create connection" [ref=e12]\n'
)


class _FakeMCPClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, args: dict) -> str:
        self.calls.append((name, args))
        return _SNAPSHOT


class _FakeAIProvider:
    def __init__(self, decisions: list[LiveExplorationDecision]) -> None:
        self._decisions = decisions
        self.is_heal_calls: list[bool] = []

    async def decide_live_exploration_action(
        self, requirement, history, snapshot, *, is_heal=False
    ) -> LiveExplorationDecision:
        self.is_heal_calls.append(is_heal)
        return self._decisions[len(self.is_heal_calls) - 1]


async def test_stops_when_goal_satisfied() -> None:
    mcp_client = _FakeMCPClient()
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"element": "Create connection button", "ref": "e12"},
                rationale="click create",
                goal_satisfied=False,
            ),
            LiveExplorationDecision(
                tool_name="browser_snapshot", tool_args={}, rationale="verify", goal_satisfied=True
            ),
        ]
    )
    heartbeats = []

    live_flow = await run_exploration(
        mcp_client=mcp_client,
        ai_provider=ai_provider,
        requirement="Create a new MCP connection.",
        start_url="https://app.example.com/",
        max_turns=10,
        heartbeat=lambda: heartbeats.append(1),
    )

    assert live_flow.goal_satisfied is True
    assert len(live_flow.steps) == 1
    assert live_flow.steps[0].tool_name == "browser_click"
    assert live_flow.steps[0].locator_candidate == {
        "strategy": "role",
        "value": 'get_by_role("button", name="Create connection")',
        "fragile": False,
        "element_tag": "button",
    }
    assert len(heartbeats) == 3  # one for the deterministic first navigation + one per observe turn


async def test_stops_at_turn_cap_without_goal_satisfied() -> None:
    mcp_client = _FakeMCPClient()
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"ref": "e12"},
                rationale="x",
                goal_satisfied=False,
            )
            for _ in range(5)
        ]
    )

    live_flow = await run_exploration(
        mcp_client=mcp_client,
        ai_provider=ai_provider,
        requirement="x",
        start_url="https://app.example.com/",
        max_turns=3,
    )

    assert live_flow.goal_satisfied is False
    assert len(live_flow.steps) == 3


async def test_navigates_to_start_url_before_the_first_observe() -> None:
    """`[FIXED]` regression: a freshly-spawned browser starts on about:blank
    — without a deterministic first navigation, the LLM had to guess a
    `browser_navigate` target from `requirement` alone (which routinely
    never states one) and, observed live, guessed wrong."""
    mcp_client = _FakeMCPClient()
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_snapshot", tool_args={}, rationale="x", goal_satisfied=True
            )
        ]
    )

    await run_exploration(
        mcp_client=mcp_client,
        ai_provider=ai_provider,
        requirement="The tenants page shows a table of tenants.",
        start_url="https://app.example.com/tenants",
        max_turns=3,
    )

    assert mcp_client.calls[0] == (
        "browser_navigate",
        {"url": "https://app.example.com/tenants"},
    )


async def test_logs_whether_each_turn_resolved_a_locator(caplog: pytest.LogCaptureFixture) -> None:
    """Diagnostic logging — the only thing that made the "0 actions captured
    despite a real exploration run" failure inspectable at all was this line
    not existing yet. A turn whose `ref` resolves against the snapshot logs
    `ref_resolved=True`; one that doesn't (or isn't an element-targeting
    tool) logs `ref_resolved=False`."""
    mcp_client = _FakeMCPClient()
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"element": "Create connection button", "ref": "e12"},
                rationale="click create",
                goal_satisfied=False,
            ),
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"ref": "unknown-ref"},
                rationale="click something not in the snapshot",
                goal_satisfied=False,
            ),
            LiveExplorationDecision(
                tool_name="browser_snapshot", tool_args={}, rationale="verify", goal_satisfied=True
            ),
        ]
    )

    with caplog.at_level("INFO", logger="generation_worker.live_exploration.agent"):
        await run_exploration(
            mcp_client=mcp_client,
            ai_provider=ai_provider,
            requirement="Create a new MCP connection.",
            start_url="https://app.example.com/",
            max_turns=10,
        )

    turn_logs = [r.message for r in caplog.records if "live-exploration turn" in r.message]
    assert "ref_resolved=True" in turn_logs[0]
    assert "ref_resolved=False" in turn_logs[1]
    assert any("goal_satisfied" in message for message in turn_logs)
    assert any("live-exploration finished" in r.message for r in caplog.records)


async def test_page_elements_accumulate_across_turns_on_the_same_url() -> None:
    """`[FIXED]` regression: a modal/dialog opening never changes the page
    URL, so sweeping only once per distinct URL permanently missed every
    field a dialog only reveals after that first snapshot (observed live:
    a real "Add connection" dialog's fields never got captured at all,
    because the tenants-list URL was already "swept" before the dialog ever
    opened). Every turn's sweep must merge into that page's running
    inventory instead of running once and never again."""
    snapshots = iter(
        [
            # Turn 1's observe() — dialog not open yet.
            '- generic [ref=e1]:\n'
            '  - Page URL: https://app.example.com/mcp\n'
            '  - button "Add connection" [ref=e2]\n',
            # Turn 2's observe() — same URL, dialog now open, new field visible.
            '- generic [ref=e1]:\n'
            '  - Page URL: https://app.example.com/mcp\n'
            '  - button "Add connection" [ref=e2]\n'
            '  - textbox "* Endpoint URL" [ref=e3]\n',
        ]
    )

    class _FakeMCPClientWithChangingSnapshot:
        async def call_tool(self, name: str, args: dict) -> str:
            return next(snapshots) if name == "browser_snapshot" else ""

    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"ref": "e2"},
                rationale="open dialog",
                goal_satisfied=False,
            ),
            LiveExplorationDecision(
                tool_name="browser_snapshot", tool_args={}, rationale="verify", goal_satisfied=True
            ),
        ]
    )

    live_flow = await run_exploration(
        mcp_client=_FakeMCPClientWithChangingSnapshot(),
        ai_provider=ai_provider,
        requirement="x",
        start_url="https://app.example.com/mcp",
        max_turns=5,
    )

    swept_values = {el["value"] for el in live_flow.page_elements["https://app.example.com/mcp"]}
    assert 'get_by_role("button", name="Add connection")' in swept_values
    assert 'get_by_role("textbox", name="* Endpoint URL")' in swept_values


async def test_passes_is_heal_through_to_ai_provider() -> None:
    mcp_client = _FakeMCPClient()
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_snapshot", tool_args={}, rationale="x", goal_satisfied=True
            )
        ]
    )

    await run_exploration(
        mcp_client=mcp_client,
        ai_provider=ai_provider,
        requirement="x",
        start_url="https://app.example.com/tenants",
        is_heal=True,
        max_turns=3,
    )

    assert ai_provider.is_heal_calls == [True]
