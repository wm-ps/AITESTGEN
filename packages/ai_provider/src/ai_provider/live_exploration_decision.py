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
