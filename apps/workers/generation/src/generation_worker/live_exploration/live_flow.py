"""LiveFlowModel — the turn-by-turn record of one live-exploration session.

Everything downstream (materialize.py, LiveExploreActivity's own Journey creation) reads
only this — never the MCP client, never a raw snapshot — keeping the shape a
generation, not a browser-automation, concern.
"""

import re
from dataclasses import dataclass, field
from typing import Any

# The real `@playwright/mcp` `browser_snapshot` tool (verified live against
# 0.0.41) returns a "### Page state" block with a YAML-ish outline, one node
# per line, e.g.:
#   - generic [ref=e2]:
#   - heading "Example Domain" [level=1] [ref=e3]
#   - paragraph [ref=e4]: This domain is for use in documentation examples...
#   - link "Learn more" [ref=e6] [cursor=pointer]:
# Two things the original regex got wrong, corrected here: (1) a node often
# has NO quoted name at all (generic/paragraph containers) — never require
# one; (2) `[ref=...]` is just one of possibly several bracket attributes
# ([level=1], [cursor=pointer]) that can appear before OR after it — never
# assume it's adjacent to the name. Extracted independently instead of one
# fixed-order regex.
_LINE_ROLE = re.compile(r"^\s*-\s*(?P<role>[a-zA-Z][\w-]*)\b")
_QUOTED_NAME = re.compile(r'"([^"]*)"')
_BRACKET_ATTR = re.compile(r"\[(\w+)=([^\]]*)\]")

# Playwright's own fragile-selector heuristics (auto-generated class names,
# numeric/hash-shaped ids) mirrored from `locator_capture`'s judgment call —
# duplicated rather than imported since `locator_capture` requires a live
# Playwright `Locator` object this module never has (the MCP subprocess owns
# the real browser, not this process).
_FRAGILE_VALUE = re.compile(r"[0-9a-f]{6,}|css-[a-z0-9]+|_ngcontent|jsx-\d+")


def find_snapshot_node(snapshot_text: str, ref: str) -> dict[str, str] | None:
    """Look up a `ref` the agent's decision named against the CURRENT raw
    snapshot text, returning its role/accessible-name — never trust a `ref`
    without confirming it's actually present in this turn's snapshot."""
    for line in snapshot_text.splitlines():
        role_match = _LINE_ROLE.match(line)
        if role_match is None:
            continue
        line_ref = next(
            (value for key, value in _BRACKET_ATTR.findall(line) if key == "ref"), None
        )
        if line_ref != ref:
            continue
        name_match = _QUOTED_NAME.search(line)
        return {
            "role": role_match.group("role"),
            "name": name_match.group(1) if name_match else "",
            "ref": ref,
        }
    return None


# Widget-shaped ARIA roles worth inventorying from a full snapshot sweep —
# structural/decorative roles (generic, group, list, row, ...) are noise for
# this purpose. Field-shaped roles (an actual value the app collects) get
# split from action-shaped ones (trigger something, collect nothing) by the
# caller — see FIELD_ROLES below.
_INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "combobox",
        "checkbox",
        "radio",
        "searchbox",
        "spinbutton",
        "switch",
        "option",
        "menuitem",
        "tab",
    }
)
FIELD_ROLES = frozenset(
    {"textbox", "combobox", "checkbox", "radio", "searchbox", "spinbutton", "switch"}
)


def sweep_interactive_nodes(snapshot_text: str) -> list[dict[str, str]]:
    """Every interactive-role node in the CURRENT snapshot — a full,
    DOM-wide inventory (role/name/ref), not just the one ref an agent's
    decision happened to name this turn. This is what a crawler's own page
    scan finds; without it, a live-exploration Page only ever knows about
    the handful of elements the agent's own turn-by-turn choices touched,
    never the rest of the page's real fields/buttons.

    A plain, no-ARIA-role `<div>` computes to role "generic" — normally
    structural noise, EXCEPT a custom clickable widget (e.g. a component
    library's dropdown option) is very often exactly this: no semantic role
    at all, just a styled div. `[cursor=pointer]` (verified live against a
    real such case — see `natural_language_flow.png`-era debugging) is the
    one signal a text-only ARIA snapshot actually gives for "this generic
    node is really interactive" — included on that basis alone, not for
    every generic node, which would otherwise flood this with every
    container on the page."""
    nodes = []
    for line in snapshot_text.splitlines():
        role_match = _LINE_ROLE.match(line)
        if role_match is None:
            continue
        role = role_match.group("role")
        bracket_attrs = dict(_BRACKET_ATTR.findall(line))
        is_clickable_generic = role == "generic" and bracket_attrs.get("cursor") == "pointer"
        if role not in _INTERACTIVE_ROLES and not is_clickable_generic:
            continue
        ref = bracket_attrs.get("ref")
        if ref is None:
            continue
        name_match = _QUOTED_NAME.search(line)
        nodes.append({"role": role, "name": name_match.group(1) if name_match else "", "ref": ref})
    return nodes


def snapshot_node_to_locator_candidate(node: dict[str, str]) -> dict[str, Any]:
    """One candidate shaped `{"strategy", "value", "fragile", "element_tag"}`
    — the superset of `Action.locator_candidates`'s `{strategy, value,
    fragile}` and `generate_playwright(..., live_inspection_locators=...)`'s
    `{strategy, value, fragile, element_tag}` (hosted.py's
    `_describe_live_locators`). Callers that write to `Action.locator_candidates`
    must drop `element_tag`; `live_inspection_locators` callers pass all four
    keys through unchanged."""
    role, name = node["role"], node["name"]
    if role == "generic":
        # `[FIXED]` A plain `<div>` (a custom widget's dropdown/menu option,
        # most commonly) computes an ARIA role of "generic" in the snapshot
        # `@playwright/mcp` itself reports — but real Playwright's own
        # `getByRole()` locator engine treats "generic" as name-from-content-
        # prohibited and matches it to ZERO elements, no matter how long a
        # generated test waits or scrolls. Verified live against a real
        # Ant Design dropdown: `get_by_role("generic", name="GIT")` against
        # the exact same open dropdown matched 0 elements, while
        # `get_by_text("GIT", exact=True)` matched exactly the one real,
        # visible option. A "generic"-role capture is therefore always
        # expressed as a text locator instead — the only thing that reliably
        # finds it in real generated code.
        value = f'get_by_text("{name}", exact=True)' if name else 'get_by_text("")'
        return {
            "strategy": "text",
            "value": value,
            "fragile": bool(_FRAGILE_VALUE.search(name)),
            "element_tag": role,
        }
    value = f'get_by_role("{role}", name="{name}")' if name else f'get_by_role("{role}")'
    return {
        "strategy": "role",
        "value": value,
        "fragile": bool(_FRAGILE_VALUE.search(name)),
        "element_tag": role,
    }


# Ancestor-chain depth cap for `extract_snapshot_context` — a handful of
# levels is enough to name the enclosing dialog/section/group; unbounded
# would let one deeply-nested page balloon every step's stored context for
# no added value (the nearest 1-2 ancestors are what a "Filters dialog" or
# "Tenant section" label actually lives on).
_MAX_CONTEXT_ANCESTORS = 4


def _line_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _node_at_line(line: str) -> dict[str, str] | None:
    # A snapshot's own "Page URL: ..."/"Page Title: ..." lines (the exact
    # convention `_extract_url`/`_extract_title` in agent.py already parse)
    # are page metadata, never real tree content — without this they'd
    # otherwise coincidentally match `_LINE_ROLE` (role="Page") and leak
    # into a later step's ancestors/preceding_sibling as meaningless noise.
    stripped = line.strip().lstrip("-").strip().lower()
    if stripped.startswith("page url:") or stripped.startswith("page title:"):
        return None
    role_match = _LINE_ROLE.match(line)
    if role_match is None:
        return None
    name_match = _QUOTED_NAME.search(line)
    return {"role": role_match.group("role"), "name": name_match.group(1) if name_match else ""}


def extract_snapshot_context(snapshot_text: str, ref: str) -> dict[str, Any]:
    """Best-effort structural context for one `ref` — the nearest ancestor
    chain, the immediately preceding sibling, and this node's own non-`ref`
    bracket attributes (`[expanded=true]`, `[checked=true]`, etc, whatever
    the snapshot happens to report — never a fixed list of attribute names)
    — reconstructed purely from the indentation the raw snapshot text
    already encodes (it's a nested outline, one node per line; deeper
    nodes are more indented — see the module-level format note above).

    This exists because `snapshot_node_to_locator_candidate` intentionally
    reduces a node to bare role+name to build a portable locator string —
    correct for that job, but it throws away the surrounding "which
    dialog/section/label is this actually inside" evidence the exploration
    LLM had directly in front of it the turn it acted. Two elements with
    an identical role and no accessible name (an unlabeled combobox is the
    common case) produce an identical locator candidate either way; this
    function is what lets a later step still tell them apart by where they
    actually sit, instead of by which one happened to be observed first.

    Always additive and best-effort: a caller that ignores this result
    behaves exactly as it did before this function existed — the existing
    locator candidate is never altered or removed, and an element with no
    useful ancestor/sibling/attribute evidence just returns `{}`."""
    lines = snapshot_text.splitlines()
    target_index: int | None = None
    target_indent: int | None = None
    for index, line in enumerate(lines):
        if _LINE_ROLE.match(line) is None:
            continue
        line_ref = next(
            (value for key, value in _BRACKET_ATTR.findall(line) if key == "ref"), None
        )
        if line_ref == ref:
            target_index = index
            target_indent = _line_indent(line)
            break
    if target_index is None or target_indent is None:
        return {}

    # Ancestors: walk backward, recording the nearest line seen so far at
    # each strictly smaller indent than the last one recorded — the
    # standard technique for recovering a breadcrumb path from an indented
    # outline, since indentation is the only structure this text format has.
    ancestors: list[dict[str, str]] = []
    current_indent = target_indent
    for index in range(target_index - 1, -1, -1):
        if current_indent <= 0 or len(ancestors) >= _MAX_CONTEXT_ANCESTORS:
            break
        line_indent = _line_indent(lines[index])
        if line_indent < current_indent:
            node = _node_at_line(lines[index])
            if node is not None:
                ancestors.append(node)
            current_indent = line_indent

    # Preceding sibling: the nearest earlier line at exactly the target's
    # own indent — a common "label text right before its control" pattern
    # (both children of the same parent), the cheapest available signal for
    # a control that has no accessible name of its own.
    preceding_sibling: dict[str, str] | None = None
    for index in range(target_index - 1, -1, -1):
        line_indent = _line_indent(lines[index])
        if line_indent < target_indent:
            break
        if line_indent == target_indent:
            preceding_sibling = _node_at_line(lines[index])
            break

    attributes = {
        key: value for key, value in _BRACKET_ATTR.findall(lines[target_index]) if key != "ref"
    }

    context: dict[str, Any] = {}
    if ancestors:
        context["ancestors"] = ancestors
    if preceding_sibling is not None:
        context["preceding_sibling"] = preceding_sibling
    if attributes:
        context["attributes"] = attributes
    return context


@dataclass
class LiveFlowStep:
    """One agent turn: the tool call it made and what it was acting on."""

    tool_name: str
    tool_args: dict[str, Any]
    rationale: str
    page_url: str | None = None
    page_heading: str | None = None
    # Populated only for element-targeting tools (click/type/select_option/
    # hover) — the node the agent's `ref` resolved to in the turn's snapshot.
    locator_candidate: dict[str, Any] | None = None
    # `[ADDED semantic-target]` What the decide-agent said this turn's action
    # MEANS (see `ai_provider.LiveExplorationDecision.semantic_target`) —
    # the user-intent identity (action/target name/value/relationship),
    # carried alongside `locator_candidate` (the DOM realization of that
    # intent) rather than merged into it. Optional and best-effort.
    semantic_target: dict[str, Any] | None = None


@dataclass
class LiveFlowModel:
    """The full record of one exploration (or heal) session, in step order.
    `materialize.py` is the only consumer that turns this into DB rows."""

    requirement: str
    steps: list[LiveFlowStep] = field(default_factory=list)
    goal_satisfied: bool = False
    # Full per-page element inventory (see `sweep_interactive_nodes`) — every
    # interactive element the ARIA snapshot exposed for a page, keyed by
    # page_url, populated once per distinct page (not per turn). Each entry
    # is a `snapshot_node_to_locator_candidate` result plus `"name"`. This is
    # what makes a live-exploration Page's known_locators/required_fields
    # comparable to a crawled Page's own Form/FormField data — `steps` alone
    # only ever covers what the agent happened to act on.
    page_elements: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def ordered_pages(self) -> list[tuple[str, str | None]]:
        """Distinct (url, heading) pairs in first-visited order — collapses
        consecutive steps performed on the same page into one entry."""
        pages: list[tuple[str, str | None]] = []
        for step in self.steps:
            if step.page_url is None:
                continue
            if pages and pages[-1][0] == step.page_url:
                continue
            pages.append((step.page_url, step.page_heading))
        return pages
