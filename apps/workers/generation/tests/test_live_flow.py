from generation_worker.live_exploration.live_flow import (
    FIELD_ROLES,
    LiveFlowModel,
    LiveFlowStep,
    find_snapshot_node,
    snapshot_node_to_locator_candidate,
    sweep_interactive_nodes,
)

_SNAPSHOT = (
    '- generic [ref=e1]:\n'
    '  - button "Create connection" [ref=e12]\n'
    '  - link "Tenants" [ref=e15]\n'
)

# Verified live against the real `@playwright/mcp@0.0.41` server (see
# scratchpad/inspect_mcp_snapshot.py) — the original regex assumed a name was
# always present and that `[ref=...]` always came immediately after it. Real
# output breaks both assumptions: many nodes have no quoted name at all, and
# other bracket attributes ([level=1], [cursor=pointer]) can appear before or
# after `[ref=...]` in either order.
_REAL_SNAPSHOT = (
    '### Page state\n'
    '- Page URL: https://example.com/\n'
    '- Page Title: Example Domain\n'
    '- Page Snapshot:\n'
    '```yaml\n'
    '- generic [ref=e2]:\n'
    '  - heading "Example Domain" [level=1] [ref=e3]\n'
    '  - paragraph [ref=e4]: This domain is for use in documentation examples.\n'
    '  - paragraph [ref=e5]:\n'
    '    - link "Learn more" [ref=e6] [cursor=pointer]:\n'
    '      - /url: https://iana.org/domains/example\n'
    '```\n'
)


def test_find_snapshot_node_matches_by_ref() -> None:
    node = find_snapshot_node(_SNAPSHOT, "e12")

    assert node == {"role": "button", "name": "Create connection", "ref": "e12"}


def test_find_snapshot_node_returns_none_for_unknown_ref() -> None:
    assert find_snapshot_node(_SNAPSHOT, "e999") is None


def test_find_snapshot_node_matches_a_node_with_no_quoted_name() -> None:
    node = find_snapshot_node(_REAL_SNAPSHOT, "e4")

    assert node == {"role": "paragraph", "name": "", "ref": "e4"}


def test_find_snapshot_node_matches_when_ref_precedes_another_bracket_attr() -> None:
    node = find_snapshot_node(_REAL_SNAPSHOT, "e6")

    assert node == {"role": "link", "name": "Learn more", "ref": "e6"}


def test_find_snapshot_node_matches_when_ref_follows_another_bracket_attr() -> None:
    node = find_snapshot_node(_REAL_SNAPSHOT, "e3")

    assert node == {"role": "heading", "name": "Example Domain", "ref": "e3"}


def test_snapshot_node_to_locator_candidate_builds_role_selector() -> None:
    node = {"role": "button", "name": "Create connection", "ref": "e12"}

    candidate = snapshot_node_to_locator_candidate(node)

    assert candidate == {
        "strategy": "role",
        "value": 'get_by_role("button", name="Create connection")',
        "fragile": False,
        "element_tag": "button",
    }


def test_snapshot_node_to_locator_candidate_omits_name_filter_when_blank() -> None:
    node = {"role": "paragraph", "name": "", "ref": "e4"}

    candidate = snapshot_node_to_locator_candidate(node)

    assert candidate["value"] == 'get_by_role("paragraph")'


def test_snapshot_node_to_locator_candidate_flags_fragile_names() -> None:
    node = {"role": "generic", "name": "css-a1b2c3", "ref": "e9"}

    candidate = snapshot_node_to_locator_candidate(node)

    assert candidate["fragile"] is True


def test_snapshot_node_to_locator_candidate_builds_text_selector_for_generic_role() -> None:
    # `[FIXED]` A "generic" role (a plain <div>, e.g. a custom dropdown's
    # option) never matches via real Playwright's `getByRole()` — verified
    # live: `get_by_role("generic", name="GIT")` matched 0 elements against a
    # real, open, on-screen Ant Design dropdown, while
    # `get_by_text("GIT", exact=True)` matched the one real, visible option.
    node = {"role": "generic", "name": "GIT", "ref": "e20"}

    candidate = snapshot_node_to_locator_candidate(node)

    assert candidate == {
        "strategy": "text",
        "value": 'get_by_text("GIT", exact=True)',
        "fragile": False,
        "element_tag": "generic",
    }


def test_sweep_interactive_nodes_finds_every_widget_not_just_one_ref() -> None:
    snapshot = (
        '- generic [ref=e1]:\n'
        '  - heading "Add MCP connection" [level=2] [ref=e2]\n'
        '  - textbox "* Endpoint URL" [ref=e3]\n'
        '  - button "Add connection" [ref=e4]\n'
        '  - paragraph [ref=e5]: Some help text\n'
    )

    nodes = sweep_interactive_nodes(snapshot)

    assert nodes == [
        {"role": "textbox", "name": "* Endpoint URL", "ref": "e3"},
        {"role": "button", "name": "Add connection", "ref": "e4"},
    ]


def test_sweep_interactive_nodes_includes_clickable_generic_nodes() -> None:
    """Verified live: a custom dropdown option (Ant Design's `<Select>`, in
    the observed case) has no ARIA role at all — plain `<div>`, so it
    computes to role "generic" — but does carry `[cursor=pointer]`, the one
    signal a text-only snapshot gives that it's really interactive."""
    snapshot = (
        '- generic [ref=e1]:\n'
        '  - generic [ref=e2]: Some inert wrapper\n'
        '  - generic "GIT" [ref=e3] [cursor=pointer]\n'
    )

    nodes = sweep_interactive_nodes(snapshot)

    assert nodes == [{"role": "generic", "name": "GIT", "ref": "e3"}]


def test_field_roles_split_from_action_roles() -> None:
    assert FIELD_ROLES == {"textbox", "combobox", "checkbox", "radio", "searchbox", "spinbutton", "switch"}
    assert "button" not in FIELD_ROLES
    assert "link" not in FIELD_ROLES


def test_ordered_pages_collapses_consecutive_same_page_steps() -> None:
    model = LiveFlowModel(
        requirement="x",
        steps=[
            LiveFlowStep(
                "browser_navigate", {}, "go to tenants",
                page_url="/tenants", page_heading="Tenants",
            ),
            LiveFlowStep(
                "browser_click", {}, "open settings",
                page_url="/tenants", page_heading="Tenants",
            ),
            LiveFlowStep(
                "browser_click", {}, "create",
                page_url="/tenants/mcp", page_heading="MCP Connections",
            ),
        ],
    )

    assert model.ordered_pages() == [("/tenants", "Tenants"), ("/tenants/mcp", "MCP Connections")]
