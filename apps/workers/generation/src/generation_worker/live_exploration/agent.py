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
import re
import time
from collections import deque
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

# Same tool on the same semantic target this many times within the last
# _STALL_WINDOW actions: tell the model in its history; past
# _STALL_STOP_REPEATS: stop the exploration as blocked.
_STALL_WINDOW = 15
_STALL_NUDGE_REPEATS = 3
_STALL_STOP_REPEATS = 6


class _AgentState(TypedDict):
    turn: int
    last_snapshot: str
    decision_tool_name: str
    decision_tool_args: dict
    decision_rationale: str
    decision_semantic_target: dict | None
    decision_exploration_scope: dict | None
    decision_current_case: str | None
    done: bool


def _is_redundant_representative_action(
    exploration_scope: dict | None, explored_collections: set[str]
) -> bool:
    """The deterministic half of the exploration-scope policy (see
    `ai_provider.LiveExplorationDecision.exploration_scope` and the
    "representative" prompt policy in hosted.py) — the LLM is asked to stop
    sampling a collection after one representative item, but a prompt is
    only ever a suggestion. This is the actual bounded guard: once one
    "representative"-scoped action against a named collection has run this
    exploration, a second one for the *same* collection is refused
    regardless of what the model decides next. "specific_item"/"dataset"
    scopes, or a turn with no named collection, are never blocked here."""
    if not exploration_scope or exploration_scope.get("scope") != "representative":
        return False
    collection = exploration_scope.get("collection")
    return bool(collection) and collection in explored_collections


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


def _case_key(name: str) -> str:
    normalized = " ".join(name.lower().split())
    # "TC6 – Verify X" → "tc6": a leading id token (has a digit) is the
    # case's identity — the agent re-types the title differently turn to
    # turn (observed: "…in AI Stu" and "…in AI Studio" for one case).
    first = re.split(r"[\s:–—-]+", normalized, maxsplit=1)[0]
    return first if any(ch.isdigit() for ch in first) else normalized


def _known_case(name: str, known: list[str]) -> str | None:
    """The already-recorded spelling of `name`'s case, if any."""
    key = _case_key(name)
    for existing in known:
        existing_key = _case_key(existing)
        if existing_key == key:
            return existing
        # Untitled-by-id cases: a truncated retyping is a prefix of the full
        # title. Never for id tokens — "tc1" is a prefix of "tc10".
        is_id = " " not in key and " " not in existing_key
        if not is_id and (existing_key.startswith(key) or key.startswith(existing_key)):
            return existing
    return None


def _canonical_case(name: str, seen: list[str]) -> str:
    known = _known_case(name, seen)
    if known is None:
        seen.append(name)
        return name
    return known


def _tag_untagged_steps(live_flow: LiveFlowModel, case_name: str, *, completed: bool) -> None:
    """A completed/skipped marker arrives the turn the agent moves on, so
    every step since the previous marker belonged to that case. Runs before
    this turn's own action is recorded — that action starts the next case."""
    for step in live_flow.steps:
        if step.test_case is None:
            step.test_case = case_name
            step.test_case_completed = completed


_RAN_CODE_RE = re.compile(
    r"^\s*await page\.(?P<locator>.+)\.(?:click|dblclick|fill|hover|selectOption|press"
    r"|pressSequentially|check|uncheck|setInputFiles)\(.*$",
    re.MULTILINE,
)


def _ran_playwright_locator(tool_result: str) -> str | None:
    """The locator Playwright MCP reports it actually ran ("### Ran
    Playwright code" → `await page.getByTitle('Preview').click();`) —
    Playwright's own generator, proven against the live element. Our
    snapshot-node conversion guesses from the accessible name instead
    (observed: an icon button titled "Preview" became getByText('Preview'),
    which matches nothing on the real page)."""
    match = _RAN_CODE_RE.search(tool_result or "")
    return match.group("locator") if match else None


def _notable_result(tool_name: str, result: str) -> str | None:
    """The part of an MCP tool's reply the agent must see next turn: an
    error (otherwise it retries the same dead ref forever) or a tab list."""
    if tool_name == "browser_tabs":
        return result[:600]
    lowered = result.lower()
    if "error" in lowered or "tool call failed" in lowered or "timeout" in lowered:
        return result[:300]
    return None


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
) -> LiveFlowModel:
    live_flow = LiveFlowModel(requirement=requirement)
    history: list[dict] = []
    # Exploration-scope guard state (see `_is_redundant_representative_action`)
    # — collection names already sampled once at "representative" scope this
    # run. Deliberately run-scoped, not turn-scoped: the whole point is
    # remembering across turns that Tenant's one representative row has
    # already been explored.
    explored_collections: set[str] = set()
    recent_attempts: deque[tuple[str, str]] = deque(maxlen=_STALL_WINDOW)
    # Stall-guard strikes since the last skipped test case (see act()).
    stall = {"strikes": 0}
    # Every case name the agent has used, first spelling wins (see
    # `_canonical_case`).
    seen_cases: list[str] = []

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
        )
        state["decision_tool_name"] = decision.tool_name
        state["decision_tool_args"] = decision.tool_args
        state["decision_rationale"] = decision.rationale
        state["decision_semantic_target"] = decision.semantic_target
        state["decision_exploration_scope"] = decision.exploration_scope
        state["decision_current_case"] = (
            _canonical_case(decision.current_case, seen_cases) if decision.current_case else None
        )
        state["done"] = decision.goal_satisfied
        skipped = decision.skipped_case
        known_names = live_flow.completed_cases + [c["name"] for c in live_flow.skipped_cases]
        if skipped and _known_case(skipped["name"], known_names) is None:
            live_flow.skipped_cases.append(skipped)
            _tag_untagged_steps(live_flow, skipped["name"], completed=False)
            history.append(
                {
                    "tool_name": None,
                    "tool_args": {},
                    "rationale": f"Skipped {skipped['name']}: {skipped['reason']}",
                    "semantic_target": None,
                }
            )
            # A new test case starts here — its repeats aren't the old one's.
            recent_attempts.clear()
            stall["strikes"] = 0
            logger.info("live-exploration: skipped case %r reason=%r", skipped["name"], skipped["reason"])
        if decision.completed_case:
            same = _known_case(decision.completed_case, live_flow.completed_cases)
            if same is None:
                live_flow.completed_cases.append(decision.completed_case)
                logger.info("live-exploration: completed case %r", decision.completed_case)
            # A repeat marker for the same case still claims the steps since
            # (the agent re-confirming it), under the first spelling.
            _tag_untagged_steps(live_flow, same or decision.completed_case, completed=True)
        if decision.blocked_reason and not decision.goal_satisfied:
            if live_flow.completed_cases:
                # Multi-case run with real progress: the block ends exploring,
                # it doesn't throw away the cases already done (observed: TC1-9
                # handled, TC10's preview down, all ten lost).
                live_flow.skipped_cases.append(
                    {"name": "Remaining test cases", "reason": decision.blocked_reason}
                )
                live_flow.goal_satisfied = True
            else:
                live_flow.blocked_reason = decision.blocked_reason
            state["done"] = True
        return state

    async def act(state: _AgentState) -> _AgentState:
        state["turn"] += 1
        if live_flow.blocked_reason:
            logger.info(
                "live-exploration turn %d: blocked reason=%r", state["turn"], live_flow.blocked_reason
            )
            return state
        if state["done"]:
            live_flow.goal_satisfied = True
            logger.info(
                "live-exploration turn %d: goal_satisfied rationale=%r",
                state["turn"],
                state["decision_rationale"][:120],
            )
            return state

        exploration_scope = state["decision_exploration_scope"]
        if _is_redundant_representative_action(exploration_scope, explored_collections):
            collection = exploration_scope["collection"]  # type: ignore[index]
            rationale = (
                f"Skipped: already explored one representative {collection} this run — "
                "exploration scope is 'representative', not 'dataset', so no further "
                f"{collection} items are sampled."
            )
            logger.info(
                "live-exploration turn %d: blocked redundant representative action for %r",
                state["turn"],
                collection,
            )
            history.append(
                {"tool_name": None, "tool_args": {}, "rationale": rationale, "semantic_target": None}
            )
            return state
        if exploration_scope and exploration_scope.get("scope") == "representative":
            collection = exploration_scope.get("collection")
            if collection:
                explored_collections.add(collection)

        tool_name = state["decision_tool_name"]
        tool_args = state["decision_tool_args"]

        # Stall guard: the prompt asks the model to report a blocker, but it
        # can still loop (observed: 120 turns re-searching for a project that
        # didn't exist). Same action on the same target, over and over, is
        # the signal. First nudge it via history, then stop for it.
        # Windowed, so a multi-test-case prompt that legitimately repeats
        # an action once per test case (e.g. "open AI Studio") never trips it.
        attempt_key = (tool_name, _summarize_semantic_target(state["decision_semantic_target"]))
        repeats = 0
        if tool_name not in ("browser_snapshot", "browser_wait_for"):
            recent_attempts.append(attempt_key)
            repeats = recent_attempts.count(attempt_key)
        if repeats > _STALL_STOP_REPEATS and not stall["strikes"]:
            # First stall: one stuck step shouldn't throw away every other
            # test case in the requirement (observed: TC1-8 done, stuck on
            # TC9's agent picker, whole run lost). Don't run the action; make
            # the model skip this case or report a real blocker.
            stall["strikes"] += 1
            recent_attempts.clear()
            history.append(
                {
                    "tool_name": None,
                    "tool_args": {},
                    "rationale": (
                        f"STOPPED: '{attempt_key[1]}' was tried {repeats - 1} times without "
                        "progress and will not be run again. If the requirement lists several "
                        "test cases, set skipped_case for the current one now and start the "
                        "next; otherwise set blocked_reason."
                    ),
                    "semantic_target": None,
                }
            )
            logger.info("live-exploration turn %d: stall guard strike 1 on %r", state["turn"], attempt_key)
            return state
        if repeats > _STALL_STOP_REPEATS:
            reason = (
                "Vantage got stuck on one step and stopped: "
                f"{state['decision_rationale'].rstrip('.')}. It tried this {repeats - 1} times "
                "without getting past it."
            )
            if live_flow.completed_cases:
                live_flow.skipped_cases.append({"name": "Remaining test cases", "reason": reason})
                live_flow.goal_satisfied = True
            else:
                live_flow.blocked_reason = reason
            state["done"] = True
            logger.info("live-exploration turn %d: stall guard stopped on %r", state["turn"], attempt_key)
            return state
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
        started = time.monotonic()
        tool_result = await mcp_client.call_tool(tool_name, tool_args)

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

        proven_locator = _ran_playwright_locator(tool_result) if tool_name in _ELEMENT_TOOLS else None
        if proven_locator:
            locator_candidate = {**(locator_candidate or {}), "playwright_locator": proven_locator}

        semantic_target = state["decision_semantic_target"]
        step = LiveFlowStep(
            tool_name=tool_name,
            tool_args=tool_args,
            rationale=state["decision_rationale"],
            page_url=_extract_url(state["last_snapshot"]),
            page_heading=_extract_title(state["last_snapshot"]),
            locator_candidate=locator_candidate,
            semantic_target=semantic_target,
            test_case=state["decision_current_case"],
            # How long the real app took for this step (action + settle) —
            # the generated test's timeouts are sized from it.
            took_seconds=round(time.monotonic() - started, 1),
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
                # Errors/tab lists only — a successful action's echo is noise,
                # and the next snapshot already shows its effect.
                "result": _notable_result(tool_name, tool_result)
                or (
                    f"this is attempt {repeats} of the same action — if the step can't be done "
                    "here, set blocked_reason"
                    if repeats >= _STALL_NUDGE_REPEATS
                    else None
                ),
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
        "decision_exploration_scope": None,
        "decision_current_case": None,
        "done": False,
    }
    final_state = await compiled.ainvoke(final_state, config={"recursion_limit": max_turns * 4})
    # Completed-ness is known only now (a case's marker can come after its
    # steps): a step counts toward a test only if its case was completed.
    for step in live_flow.steps:
        if step.test_case:
            step.test_case_completed = (
                _known_case(step.test_case, live_flow.completed_cases) is not None
            )

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
