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
        settle_retries=0,
    )

    assert live_flow.goal_satisfied is True
    assert len(live_flow.steps) == 1
    assert live_flow.steps[0].tool_name == "browser_click"
    assert live_flow.steps[0].locator_candidate == {
        "strategy": "role",
        "value": 'get_by_role("button", name="Create connection")',
        "fragile": False,
        "element_tag": "button",
        # `context`: the button's only real ancestor in `_SNAPSHOT` below is
        # the outer `generic [ref=e1]:` wrapper — the fixture's own
        # "Page URL: ..." line is filtered out as page metadata, not a real
        # sibling/ancestor (see `extract_snapshot_context`).
        "context": {"ancestors": [{"role": "generic", "name": ""}]},
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
        settle_retries=0,
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
        settle_retries=0,
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
            settle_retries=0,
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
        settle_retries=0,
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
        settle_retries=0,
    )

    assert ai_provider.is_heal_calls == [True]


async def test_semantic_target_carries_from_decision_into_step_and_next_turns_history() -> None:
    """`[ADDED semantic-target]` A two-turn "open Fruits, then select Mango"
    interaction: each decision's `semantic_target` must land on its own
    `LiveFlowStep` (the explicit identity, separate from the resolved
    `locator_candidate`), and the first turn's target must still be visible
    in `history` by the time the second turn's decision is requested — the
    mechanism that lets a later turn stay anchored to the same target
    instead of re-guessing it."""
    mcp_client = _FakeMCPClient()

    class _RecordingAIProvider:
        def __init__(self, decisions: list[LiveExplorationDecision]) -> None:
            self._decisions = decisions
            self.history_calls: list[list[dict]] = []

        async def decide_live_exploration_action(
            self, requirement, history, snapshot, *, is_heal=False
        ) -> LiveExplorationDecision:
            self.history_calls.append(history)
            return self._decisions[len(self.history_calls) - 1]

    ai_provider = _RecordingAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"element": "Fruits control", "ref": "e12"},
                rationale="open the Fruits control",
                goal_satisfied=False,
                semantic_target={"action": "click", "target": {"name": "Fruits"}},
            ),
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"element": "Mango option", "ref": "e12"},
                rationale="select Mango",
                goal_satisfied=False,
                semantic_target={
                    "action": "select",
                    "target": {"name": "Fruits"},
                    "value": "Mango",
                    "relationship": {"type": "value_belongs_to_target"},
                },
            ),
            LiveExplorationDecision(
                tool_name="browser_snapshot",
                tool_args={},
                rationale="verify Mango is now selected",
                goal_satisfied=True,
            ),
        ]
    )

    live_flow = await run_exploration(
        mcp_client=mcp_client,
        ai_provider=ai_provider,
        requirement="Select Mango in the Fruits dropdown.",
        start_url="https://app.example.com/",
        max_turns=10,
        settle_retries=0,
    )

    assert live_flow.steps[0].semantic_target == {"action": "click", "target": {"name": "Fruits"}}
    assert live_flow.steps[1].semantic_target == {
        "action": "select",
        "target": {"name": "Fruits"},
        "value": "Mango",
        "relationship": {"type": "value_belongs_to_target"},
    }
    # Second turn's decide() call saw the first turn's semantic target in
    # its history — the identity survived the DOM-changing action between
    # turns (opening the dropdown), not just the locator.
    second_turn_history = ai_provider.history_calls[1]
    assert second_turn_history[0]["semantic_target"] == {
        "action": "click",
        "target": {"name": "Fruits"},
    }


async def test_settles_after_a_click_before_the_next_observe() -> None:
    """`[FIXED]` regression: a click that triggers a client-side route change
    (no full page load) could still be mid-transition when the next turn's
    `observe` snapshotted the page — the LLM then saw an apparently-unchanged
    page and reissued the exact same click a second time (observed live: the
    same "MCP connections" link clicked twice in a row against a real
    application). `act` must keep re-snapshotting after a click until the
    page actually changes, so `observe`'s next snapshot is never stale."""
    snapshots = iter(
        [
            # Turn 1's observe() — pre-click.
            '- generic [ref=e1]:\n'
            '  - Page URL: https://app.example.com/tenants\n'
            '  - link "MCP connections" [ref=e2]\n',
            # act()'s first settle check — still mid-transition, unchanged.
            '- generic [ref=e1]:\n'
            '  - Page URL: https://app.example.com/tenants\n'
            '  - link "MCP connections" [ref=e2]\n',
            # act()'s second settle check — the route has now changed.
            '- generic [ref=e1]:\n'
            '  - Page URL: https://app.example.com/mcp\n',
            # Turn 2's observe() — same settled snapshot.
            '- generic [ref=e1]:\n'
            '  - Page URL: https://app.example.com/mcp\n',
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
                rationale="follow the MCP connections link",
                goal_satisfied=False,
            ),
            LiveExplorationDecision(
                tool_name="browser_snapshot", tool_args={}, rationale="verify", goal_satisfied=True
            ),
        ]
    )

    await run_exploration(
        mcp_client=_FakeMCPClientWithChangingSnapshot(),
        ai_provider=ai_provider,
        requirement="x",
        start_url="https://app.example.com/tenants",
        max_turns=5,
        settle_retries=3,
        settle_delay_seconds=0,
    )

    # goal_satisfied on turn 2 proves the LLM was shown the settled
    # (post-navigation) snapshot, not the stale pre-navigation one it would
    # have seen without the settle retry.
    assert next(snapshots, None) is None


class TestExplorationScope:
    """`[ADDED exploration-scope]` The deterministic half of the policy (see
    `agent._is_redundant_representative_action` and
    `ai_provider.LiveExplorationDecision.exploration_scope`) — whatever the
    model decides, a second "representative"-scoped action against a
    collection already sampled once this run must never actually execute."""

    async def test_representative_scope_action_executes_normally(self) -> None:
        """Scenario: "Open tenant settings." — representative exploration is
        sufficient; the one action for it executes like any other."""
        mcp_client = _FakeMCPClient()
        ai_provider = _FakeAIProvider(
            [
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale="open the first tenant's settings",
                    goal_satisfied=False,
                    exploration_scope={"collection": "Tenant", "scope": "representative"},
                ),
                LiveExplorationDecision(
                    tool_name="browser_snapshot",
                    tool_args={},
                    rationale="verify",
                    goal_satisfied=True,
                ),
            ]
        )

        live_flow = await run_exploration(
            mcp_client=mcp_client,
            ai_provider=ai_provider,
            requirement="Open tenant settings.",
            start_url="https://app.example.com/tenants",
            max_turns=5,
            settle_retries=0,
        )

        assert len(live_flow.steps) == 1
        assert live_flow.steps[0].tool_name == "browser_click"

    async def test_second_representative_action_for_same_collection_is_blocked(self) -> None:
        """The deterministic circuit breaker: once one "representative"
        action against "Tenant" has run, a second one for the same
        collection is refused regardless of what the model decides next —
        an actual bounded policy, not just an LLM instruction."""
        mcp_client = _FakeMCPClient()
        ai_provider = _FakeAIProvider(
            [
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale="open the first tenant row",
                    goal_satisfied=False,
                    exploration_scope={"collection": "Tenant", "scope": "representative"},
                ),
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale="open a second tenant row",
                    goal_satisfied=False,
                    exploration_scope={"collection": "Tenant", "scope": "representative"},
                ),
            ]
        )

        live_flow = await run_exploration(
            mcp_client=mcp_client,
            ai_provider=ai_provider,
            requirement="Open tenant settings.",
            start_url="https://app.example.com/tenants",
            max_turns=2,
            settle_retries=0,
        )

        click_calls = [c for c in mcp_client.calls if c[0] == "browser_click"]
        assert len(click_calls) == 1
        assert len(live_flow.steps) == 1

    async def test_specific_item_scope_is_never_blocked(self) -> None:
        """Scenario: "Open the third tenant's settings." — a bounded/
        specific request is never refused by the representative-collision
        guard, even naming the same collection as an earlier representative
        sample."""
        mcp_client = _FakeMCPClient()
        ai_provider = _FakeAIProvider(
            [
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale="open the first tenant row (representative)",
                    goal_satisfied=False,
                    exploration_scope={"collection": "Tenant", "scope": "representative"},
                ),
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale="open the third tenant row, as explicitly requested",
                    goal_satisfied=False,
                    exploration_scope={"collection": "Tenant", "scope": "specific_item"},
                ),
            ]
        )

        live_flow = await run_exploration(
            mcp_client=mcp_client,
            ai_provider=ai_provider,
            requirement="Open the third tenant's settings.",
            start_url="https://app.example.com/tenants",
            max_turns=2,
            settle_retries=0,
        )

        click_calls = [c for c in mcp_client.calls if c[0] == "browser_click"]
        assert len(click_calls) == 2
        assert len(live_flow.steps) == 2

    async def test_dataset_scope_is_never_blocked(self) -> None:
        """Scenario: "Validate every tenant's settings." — dataset-wide
        coverage means every action against the collection runs, not just
        one representative."""
        mcp_client = _FakeMCPClient()
        ai_provider = _FakeAIProvider(
            [
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale=f"open tenant row {i}",
                    goal_satisfied=False,
                    exploration_scope={"collection": "Tenant", "scope": "dataset"},
                )
                for i in range(3)
            ]
        )

        live_flow = await run_exploration(
            mcp_client=mcp_client,
            ai_provider=ai_provider,
            requirement="Validate every tenant's settings.",
            start_url="https://app.example.com/tenants",
            max_turns=3,
            settle_retries=0,
        )

        click_calls = [c for c in mcp_client.calls if c[0] == "browser_click"]
        assert len(click_calls) == 3
        assert len(live_flow.steps) == 3

    async def test_dataset_scope_allows_pagination_traversal(self) -> None:
        """Scenario: "Check all pages of the transaction history." —
        pagination is just more of the same collection under dataset scope;
        clicking through multiple pages must not be blocked."""
        mcp_client = _FakeMCPClient()
        ai_provider = _FakeAIProvider(
            [
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale=f"go to page {i}",
                    goal_satisfied=False,
                    exploration_scope={"collection": "TransactionHistoryPage", "scope": "dataset"},
                )
                for i in range(1, 4)
            ]
        )

        await run_exploration(
            mcp_client=mcp_client,
            ai_provider=ai_provider,
            requirement="Check all pages of the transaction history.",
            start_url="https://app.example.com/transactions",
            max_turns=3,
            settle_retries=0,
        )

        click_calls = [c for c in mcp_client.calls if c[0] == "browser_click"]
        assert len(click_calls) == 3

    async def test_fresh_exploration_run_is_not_restricted_by_prior_discovery_sampling(
        self,
    ) -> None:
        """Scenario: initial discovery samples one representative row, then
        Live Exploration explicitly requests a specific row — this module
        never reads crawler/discovery DB data at all (see the module
        docstring) and the guard's `explored_collections` set is created
        fresh inside `run_exploration` every call, so nothing from any
        other run (discovery's or a prior Live Exploration run) can ever
        restrict this one."""
        mcp_client = _FakeMCPClient()
        ai_provider = _FakeAIProvider(
            [
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale="open the specific tenant requested",
                    goal_satisfied=False,
                    exploration_scope={"collection": "Tenant", "scope": "specific_item"},
                ),
                LiveExplorationDecision(
                    tool_name="browser_snapshot",
                    tool_args={},
                    rationale="verify",
                    goal_satisfied=True,
                ),
            ]
        )

        live_flow = await run_exploration(
            mcp_client=mcp_client,
            ai_provider=ai_provider,
            requirement="Open the tenant named Acme Corp.",
            start_url="https://app.example.com/tenants",
            max_turns=3,
            settle_retries=0,
        )

        assert len(live_flow.steps) == 1
        assert live_flow.steps[0].tool_name == "browser_click"

    async def test_non_collection_action_with_no_exploration_scope_is_unaffected(self) -> None:
        """Backward compatibility: a decision with no `exploration_scope` at
        all (ordinary, non-collection navigation) executes exactly as it did
        before this feature existed."""
        mcp_client = _FakeMCPClient()
        ai_provider = _FakeAIProvider(
            [
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale="click the settings link",
                    goal_satisfied=False,
                    exploration_scope=None,
                ),
                LiveExplorationDecision(
                    tool_name="browser_click",
                    tool_args={"ref": "e12"},
                    rationale="click the save button",
                    goal_satisfied=False,
                    exploration_scope=None,
                ),
            ]
        )

        live_flow = await run_exploration(
            mcp_client=mcp_client,
            ai_provider=ai_provider,
            requirement="Open settings and save.",
            start_url="https://app.example.com/settings",
            max_turns=2,
            settle_retries=0,
        )

        click_calls = [c for c in mcp_client.calls if c[0] == "browser_click"]
        assert len(click_calls) == 2
        assert len(live_flow.steps) == 2


async def test_stops_with_reason_when_model_reports_blocked() -> None:
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_snapshot",
                rationale="not there",
                blocked_reason='Couldn\'t find a project named "X" on the Apps page.',
            )
        ]
    )

    live_flow = await run_exploration(
        mcp_client=_FakeMCPClient(),
        ai_provider=ai_provider,
        requirement="Open project X.",
        start_url="https://app.example.com/",
        max_turns=10,
        settle_retries=0,
    )

    assert live_flow.blocked_reason == 'Couldn\'t find a project named "X" on the Apps page.'
    assert live_flow.goal_satisfied is False
    assert live_flow.steps == []


async def test_stall_guard_stops_a_repeating_action() -> None:
    click = LiveExplorationDecision(
        tool_name="browser_click",
        tool_args={"element": "Create connection button", "ref": "e12"},
        rationale="Click Create connection",
        semantic_target={"action": "click", "target": {"name": "Create connection"}},
    )
    ai_provider = _FakeAIProvider([click] * 30)

    live_flow = await run_exploration(
        mcp_client=_FakeMCPClient(),
        ai_provider=ai_provider,
        requirement="Create a new MCP connection.",
        start_url="https://app.example.com/",
        max_turns=30,
        settle_retries=0,
    )

    # First stall only refuses the action (a chance to skip this case);
    # still stuck after that, the run stops as blocked.
    assert live_flow.blocked_reason is not None
    assert "Click Create connection" in live_flow.blocked_reason
    assert len(live_flow.steps) == 12


async def test_skipped_case_is_recorded_and_exploration_continues() -> None:
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"element": "Create connection button", "ref": "e12"},
                rationale="start TC2",
                skipped_case={"name": "TC1", "reason": "It needs a file to upload."},
            ),
            LiveExplorationDecision(tool_name="browser_snapshot", rationale="done", goal_satisfied=True),
        ]
    )

    live_flow = await run_exploration(
        mcp_client=_FakeMCPClient(),
        ai_provider=ai_provider,
        requirement="TC1 upload. TC2 create.",
        start_url="https://app.example.com/",
        max_turns=10,
        settle_retries=0,
    )

    assert live_flow.skipped_cases == [{"name": "TC1", "reason": "It needs a file to upload."}]
    assert live_flow.goal_satisfied is True
    assert live_flow.blocked_reason is None
    assert len(live_flow.steps) == 1


async def test_block_after_completed_cases_keeps_them() -> None:
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"element": "Create connection button", "ref": "e12"},
                rationale="TC1 done, start TC2",
                completed_case="TC1",
            ),
            LiveExplorationDecision(
                tool_name="browser_snapshot",
                rationale="preview down",
                blocked_reason="TC2's preview refused to connect.",
            ),
        ]
    )

    live_flow = await run_exploration(
        mcp_client=_FakeMCPClient(),
        ai_provider=ai_provider,
        requirement="TC1 create. TC2 preview.",
        start_url="https://app.example.com/",
        max_turns=10,
        settle_retries=0,
    )

    assert live_flow.blocked_reason is None
    assert live_flow.goal_satisfied is True
    assert live_flow.completed_cases == ["TC1"]
    assert live_flow.skipped_cases == [
        {"name": "Remaining test cases", "reason": "TC2's preview refused to connect."}
    ]


async def test_steps_are_tagged_with_the_case_they_belong_to() -> None:
    click = {"tool_name": "browser_click", "tool_args": {"element": "Create connection button", "ref": "e12"}}
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(**click, rationale="TC1 step"),
            LiveExplorationDecision(**click, rationale="TC2 step", completed_case="TC1"),
            LiveExplorationDecision(
                tool_name="browser_snapshot", rationale="done", goal_satisfied=True, completed_case="TC2"
            ),
        ]
    )

    live_flow = await run_exploration(
        mcp_client=_FakeMCPClient(),
        ai_provider=ai_provider,
        requirement="TC1. TC2.",
        start_url="https://app.example.com/",
        max_turns=10,
        settle_retries=0,
    )

    assert [(s.rationale, s.test_case, s.test_case_completed) for s in live_flow.steps] == [
        ("TC1 step", "TC1", True),
        ("TC2 step", "TC2", True),
    ]


def test_scenarios_are_grounded_in_their_own_case() -> None:
    from types import SimpleNamespace

    from generation_worker.activities import ground_scenarios_in_own_live_case

    flow = [
        {"value": "a", "test_case": "TC1", "test_case_completed": True},
        {"value": "b", "test_case": "TC2", "test_case_completed": False},
        {"value": "c", "test_case": "TC3", "test_case_completed": True},
    ]
    first, second = SimpleNamespace(grounding=None), SimpleNamespace(grounding=None)
    ground_scenarios_in_own_live_case(flow, [first, second])
    assert first.grounding == {"captured_flow": [flow[0]], "overlay_dismissals": []}
    assert second.grounding == {"captured_flow": [flow[2]], "overlay_dismissals": []}

    unmatched = SimpleNamespace(grounding=None)
    ground_scenarios_in_own_live_case(flow, [unmatched])
    assert unmatched.grounding is None


def test_case_name_variants_are_one_case() -> None:
    from generation_worker.live_exploration.agent import _known_case

    known = ["TC6 – Verify Apply All Functionality in AI Stu", "TC1 – Verify Login"]
    assert _known_case("TC6 – Verify Apply All Functionality in AI Studio", known) == known[0]
    assert _known_case("tc6: apply all", known) == known[0]
    assert _known_case("TC10 – Verify Preview", known) is None
    assert _known_case("Verify the checkout flow", ["Verify the checkout"]) == "Verify the checkout"
    assert _known_case("Open settings", ["Verify the checkout"]) is None


async def test_current_case_tags_steps_even_when_completion_is_marked_late() -> None:
    click = {"tool_name": "browser_click", "tool_args": {"element": "Create connection button", "ref": "e12"}}
    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(**click, rationale="TC1 step", current_case="TC1 – Create"),
            LiveExplorationDecision(**click, rationale="TC2 step", current_case="TC2 – Edit"),
            # TC1 marked done only now, a turn late.
            LiveExplorationDecision(
                **click, rationale="TC2 more", current_case="TC2 – Edit", completed_case="TC1 – Create"
            ),
            LiveExplorationDecision(
                tool_name="browser_snapshot",
                rationale="done",
                goal_satisfied=True,
                completed_case="tc2: edit",
            ),
        ]
    )

    live_flow = await run_exploration(
        mcp_client=_FakeMCPClient(),
        ai_provider=ai_provider,
        requirement="TC1. TC2.",
        start_url="https://app.example.com/",
        max_turns=10,
        settle_retries=0,
    )

    assert [(s.rationale, s.test_case, s.test_case_completed) for s in live_flow.steps] == [
        ("TC1 step", "TC1 – Create", True),
        ("TC2 step", "TC2 – Edit", True),
        ("TC2 more", "TC2 – Edit", True),
    ]


def test_ran_playwright_locator_is_taken_from_mcp_output() -> None:
    from generation_worker.live_exploration.agent import _ran_playwright_locator

    out = "### Ran Playwright code\n```js\nawait page.getByTitle('Preview').click();\n```\n### Page state"
    assert _ran_playwright_locator(out) == "getByTitle('Preview')"
    out = "```js\nawait page.getByRole('textbox', { name: 'Chat input' }).fill('Add a. heading');\n```"
    assert _ran_playwright_locator(out) == "getByRole('textbox', { name: 'Chat input' })"
    assert _ran_playwright_locator("(tool call failed: timed out)") is None


async def test_proven_locator_is_recorded_on_the_step() -> None:
    class _MCP(_FakeMCPClient):
        async def call_tool(self, name, args):
            if name == "browser_click":
                return "### Ran Playwright code\n```js\nawait page.getByTitle('Create').click();\n```"
            return await super().call_tool(name, args)

    ai_provider = _FakeAIProvider(
        [
            LiveExplorationDecision(
                tool_name="browser_click",
                tool_args={"element": "Create connection button", "ref": "e12"},
                rationale="click",
            ),
            LiveExplorationDecision(tool_name="browser_snapshot", rationale="done", goal_satisfied=True),
        ]
    )
    live_flow = await run_exploration(
        mcp_client=_MCP(),
        ai_provider=ai_provider,
        requirement="Create.",
        start_url="https://app.example.com/",
        max_turns=5,
        settle_retries=0,
    )
    assert live_flow.steps[0].locator_candidate["playwright_locator"] == "getByTitle('Create')"
