"""LiveExplorationDecision — one turn of the live-exploration agent loop.

Mirrors `journey_candidate.py`/`scenario_candidate.py`'s shape: a plain
dataclass the AIProvider port returns, converted by the caller (never by this
package) into whatever domain/Temporal types it needs.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiveExplorationDecision:
    # A Playwright MCP tool name (e.g. "browser_click", "browser_navigate") —
    # "browser_snapshot" and "browser_wait_for" are valid choices too, when
    # the agent needs another look before acting. Ignored once
    # `goal_satisfied` is true.
    tool_name: str
    tool_args: dict[str, Any] = field(default_factory=dict)
    # Short plain-language reasoning — recorded into the Live Flow Model for
    # audit, never shown to the end user as-is.
    rationale: str = ""
    goal_satisfied: bool = False
    # `[ADDED semantic-target]` What this turn's action MEANS, independent of
    # how it ends up implemented in the DOM — e.g. {"action": "select",
    # "target": {"name": "Fruits"}, "value": "Mango", "relationship":
    # {"type": "value_belongs_to_target"}}. Extracted by the same call that
    # picks `tool_name`/`tool_args`, but kept as its own field so it stays
    # the stable identity across turns (open a dropdown, then pick an option
    # from it) even as `tool_args`/the resolved locator change turn to turn.
    # Optional and best-effort — never required, never a replacement for
    # `tool_args`/the locator candidate it resolves to.
    semantic_target: dict[str, Any] | None = None
    # `[ADDED exploration-scope]` How much of a repeated collection (table
    # rows, list/grid items, paginated data) this turn's action should
    # cover — separate from `semantic_target`, which answers *which* item,
    # never *how many*: {"collection": "Tenant", "scope": "representative"}.
    # `scope` is one of "representative" (default — sample one item, then
    # stop), "specific_item" (the requirement names/bounds a particular
    # item), or "dataset" (the requirement, or a concrete Application
    # Context reason, requires broad/all-item coverage). `None` when this
    # turn isn't acting on a collection at all.
    exploration_scope: dict[str, Any] | None = None
