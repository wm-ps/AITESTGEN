"""The LangGraph live-exploration agent: observe -> decide -> act, looping
until the AIProvider reports the goal satisfied or a turn cap is hit.

LangGraph owns orchestration only (state, the loop, the stop condition) —
Playwright MCP (mcp_client.py) is the only thing that ever touches the
browser; the AIProvider (ai_provider package) is the only thing that ever
decides what to do next. Neither this module nor its state ever reads
crawler/discovery DB data.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import TypedDict

from ai_provider import AIProvider
from langgraph.graph import END, StateGraph

from generation_worker.live_exploration.live_flow import (
    LiveFlowModel,
    LiveFlowStep,
    extract_snapshot_context,
    find_snapshot_node,
    snapshot_node_to_locator_candidate,
    sweep_interactive_nodes,
)
from generation_worker.live_exploration.mcp_client import PlaywrightMCPClient

logger = logging.getLogger(__name__)

# Element-targeting tools whose `ref` argument must resolve against the
# current snapshot to yield a locator candidate for the Live Flow Model.
_ELEMENT_TOOLS = frozenset(
    {"browser_click", "browser_type", "browser_select_option", "browser_hover"}
)

# Tools that can trigger a client-side route change or other DOM mutation
# with no full page load — nothing else here waits for that to finish, so
# the very next `observe` can snapshot the page mid-transition.
_SETTLE_AFTER_TOOLS = frozenset({"browser_click", "browser_select_option"})


class _AgentState(TypedDict):
    turn: int
    last_snapshot: str
    decision_tool_name: str
    decision_tool_args: dict
    decision_rationale: str
    decision_semantic_target: dict | None
    done: bool


def _summarize_semantic_target(semantic_target: dict | None) -> str:
    """One-line debug summary — see `_AgentState.decision_semantic_target`.
    Never raises on a malformed/hallucinated shape; worst case is a blank
    summary, not a crashed turn."""
    if not semantic_target:
        return "(none)"
    target = semantic_target.get("target")
    target_name = target.get("name") if isinstance(target, dict) else None
    parts = [str(p) for p in (semantic_target.get("action"), target_name) if p]
    value = semantic_target.get("value")
    if value:
        parts.append(f"value={value!r}")
    return " ".join(parts) if parts else "(none)"


def _extract_url(snapshot_text: str) -> str | None:
    # `@playwright/mcp`'s snapshot text leads with a "- Page URL: <url>" line.
    for line in snapshot_text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if stripped.lower().startswith("page url:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _extract_title(snapshot_text: str) -> str | None:
    for line in snapshot_text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if stripped.lower().startswith("page title:"):
            return stripped.split(":", 1)[1].strip()
    return None


async def run_exploration(
    *,
    mcp_client: PlaywrightMCPClient,
    ai_provider: AIProvider,
    requirement: str,
    start_url: str,
    is_heal: bool = False,
    max_turns: int = 30,
    heartbeat: Callable[[], None] | None = None,
    settle_retries: int = 3,
    settle_delay_seconds: float = 0.4,
    # `[ADDED application-context]` `Application.application_context`,
    # verbatim — given to every turn's `decide()` call alongside the
    # requirement and live snapshot, so the agent can reason with business
    # rules/session behavior it can't discover from the DOM alone (e.g.
    # "Engagement options depend on the selected tenant"). Optional; `None`
    # behaves exactly as this call did before the parameter existed.
    application_context: dict | None = None,
) -> LiveFlowModel:
    live_flow = LiveFlowModel(requirement=requirement)
    history: list[dict] = []

    async def observe(state: _AgentState) -> _AgentState:
        if heartbeat:
            heartbeat()
        snapshot = await mcp_client.call_tool("browser_snapshot", {})
        state["last_snapshot"] = snapshot
        page_url = _extract_url(snapshot)
        # `[FIXED]` Used to sweep once per distinct URL and never again — but
        # a modal/dialog opening (the common case this exists for, e.g. "Add
        # connection") never changes the URL, so a one-time sweep permanently
        # missed every field a dialog only reveals after that first
        # snapshot. Every turn's snapshot is swept and merged into that
        # page's running inventory instead, deduped by locator value —
        # accumulates new elements as more of the page's state (dialogs,
        # expanded sections, tabs) gets revealed, never loses what an
        # earlier turn already found.
        if page_url:
            page_inventory = live_flow.page_elements.setdefault(page_url, [])
            known_values = {element["value"] for element in page_inventory}
            for node in sweep_interactive_nodes(snapshot):
                candidate = {**snapshot_node_to_locator_candidate(node), "name": node["name"]}
                if candidate["value"] not in known_values:
                    page_inventory.append(candidate)
                    known_values.add(candidate["value"])
        return state

    async def decide(state: _AgentState) -> _AgentState:
        decision = await ai_provider.decide_live_exploration_action(
            requirement,
            history,
            {"text": state["last_snapshot"]},
            is_heal=is_heal,
            application_context=application_context,
        )
        state["decision_tool_name"] = decision.tool_name
        state["decision_tool_args"] = decision.tool_args
        state["decision_rationale"] = decision.rationale
        state["decision_semantic_target"] = decision.semantic_target
        state["done"] = decision.goal_satisfied
        return state

    async def act(state: _AgentState) -> _AgentState:
        state["turn"] += 1
        if state["done"]:
            live_flow.goal_satisfied = True
            logger.info(
                "live-exploration turn %d: goal_satisfied rationale=%r",
                state["turn"],
                state["decision_rationale"][:120],
            )
            return state

        tool_name = state["decision_tool_name"]
        tool_args = state["decision_tool_args"]
        locator_candidate = None
        if tool_name in _ELEMENT_TOOLS and "ref" in tool_args:
            node = find_snapshot_node(state["last_snapshot"], tool_args["ref"])
            if node is not None:
                locator_candidate = snapshot_node_to_locator_candidate(node)
                # Additive only — `value`/`strategy`/`fragile`/`element_tag`
                # above are unchanged and still what actually resolves this
                # element; `context` is surrounding structural evidence
                # (ancestor chain, preceding sibling, non-`ref` attributes)
                # a later stage can use to disambiguate two steps that
                # otherwise resolve to the exact same locator — never
                # required, always safe to ignore.
                context = extract_snapshot_context(state["last_snapshot"], tool_args["ref"])
                if context:
                    locator_candidate["context"] = context

        pre_action_snapshot = state["last_snapshot"]
        await mcp_client.call_tool(tool_name, tool_args)

        # `[FIXED]` A click/select that triggers a client-side route change
        # (no full page load, so nothing above waits for it) could still be
        # mid-transition when the next turn's `observe` snapshots the page —
        # the LLM then saw an apparently-unchanged page and reissued the
        # exact same action a second time (observed live: the same "MCP
        # connections" link clicked twice in a row against a real
        # application). Settle here, once, right after acting: re-snapshot
        # with a short backoff until the page visibly moves on, so the next
        # observe never hands the LLM a stale snapshot it can mistake for
        # its action having done nothing.
        if tool_name in _SETTLE_AFTER_TOOLS:
            for _ in range(settle_retries):
                if settle_delay_seconds:
                    await asyncio.sleep(settle_delay_seconds)
                settled_snapshot = await mcp_client.call_tool("browser_snapshot", {})
                if settled_snapshot != pre_action_snapshot:
                    break

        semantic_target = state["decision_semantic_target"]
        step = LiveFlowStep(
            tool_name=tool_name,
            tool_args=tool_args,
            rationale=state["decision_rationale"],
            page_url=_extract_url(state["last_snapshot"]),
            page_heading=_extract_title(state["last_snapshot"]),
            locator_candidate=locator_candidate,
            semantic_target=semantic_target,
        )
        live_flow.steps.append(step)
        logger.info(
            "live-exploration turn %d: tool=%s ref_resolved=%s page=%s semantic_target=%s "
            "rationale=%r",
            state["turn"],
            tool_name,
            tool_name in _ELEMENT_TOOLS and "ref" in tool_args and locator_candidate is not None,
            step.page_url,
            _summarize_semantic_target(semantic_target),
            step.rationale[:120],
        )
        history.append(
            {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "rationale": step.rationale,
                "semantic_target": semantic_target,
            }
        )
        return state

    def route_after_act(state: _AgentState) -> str:
        if state["done"] or state["turn"] >= max_turns:
            return END
        return "observe"

    graph = StateGraph(_AgentState)
    graph.add_node("observe", observe)
    graph.add_node("decide", decide)
    graph.add_node("act", act)
    graph.set_entry_point("observe")
    graph.add_edge("observe", "decide")
    graph.add_edge("decide", "act")
    graph.add_conditional_edges("act", route_after_act, {"observe": "observe", END: END})
    compiled = graph.compile()

    # `[FIXED]` A freshly-spawned browser starts on about:blank — without a
    # deterministic first navigation here, turn 1's `observe` snapshots that
    # blank page and the LLM has to guess a `browser_navigate` target from
    # `requirement` alone (which routinely never states one at all, e.g. "the
    # tenants page shows a table..."). Observed live: the agent guessed wrong,
    # landed on a `chrome-error://` page, and burned its entire turn budget
    # never reaching the real app. Same "never leave the first navigation to
    # LLM judgment" rule `_PLAYWRIGHT_PROMPT_SYSTEM`'s own
    # `initial_navigation_rule` already enforces for code generation.
    if heartbeat:
        heartbeat()
    await mcp_client.call_tool("browser_navigate", {"url": start_url})

    final_state: _AgentState = {
        "turn": 0,
        "last_snapshot": "",
        "decision_tool_name": "",
        "decision_tool_args": {},
        "decision_rationale": "",
        "decision_semantic_target": None,
        "done": False,
    }
    await compiled.ainvoke(final_state, config={"recursion_limit": max_turns * 4})

    logger.info(
        "live-exploration finished: goal_satisfied=%s steps=%d turns=%d/%d requirement=%r is_heal=%s",
        live_flow.goal_satisfied,
        len(live_flow.steps),
        final_state["turn"],
        max_turns,
        requirement,
        is_heal,
    )
    if not live_flow.goal_satisfied:
        logger.warning(
            "live-exploration agent stopped without goal_satisfied after %d turns "
            "(requirement=%r, is_heal=%s)",
            max_turns,
            requirement,
            is_heal,
        )
    return live_flow
