"""Explorer's recorded actions reach Vantage's generator in its own
live-flow shape (promote.captured_flow)."""

import uuid

from domain import Component, ComponentLocator, Form, FormField, Page
from explorer_core import ExplorerScreen
from explorer_worker.promote import (
    _persist_screen_model,
    _proof_sentence,
    _test_data,
    captured_flow,
)


def test_recorded_actions_become_generator_steps() -> None:
    flow = captured_flow(
        [
            {"do": "goto", "url": "https://app/#/start"},
            {"do": "fill", "field": "Policy number", "value": "P-1"},
            {"do": "choose", "field": "Hurt?", "option": "No one was hurt"},
            {"do": "click", "label": "Continue"},
        ]
    )
    assert [s["tool_name"] for s in flow] == [
        "browser_navigate",
        "browser_type",
        "browser_click",
        "browser_click",
    ]
    assert flow[1]["value"] == 'get_by_label("Policy number")'
    assert flow[1]["semantic_target"]["value"] == "P-1"
    assert flow[2]["value"] == 'get_by_text("No one was hurt", exact=True)'
    assert flow[3]["value"] == 'get_by_role("button", name="Continue")'
    assert all(s["value"] for s in flow)  # the generator drops steps without one


def test_proof_sentence() -> None:
    assert (
        _proof_sentence({"kind": "text_visible", "value": "Saved"})
        == " Proof of success: the screen shows “Saved”."
    )
    assert _proof_sentence(None) == ""


class _Collect:
    """Stands in for a Session: records what promote would write."""

    def __init__(self) -> None:
        self.rows: list[object] = []

    def add(self, row: object) -> None:
        self.rows.append(row)

    def flush(self) -> None:
        pass


def test_screen_model_feeds_self_healing_in_the_crawler_shape() -> None:
    app_id, run_id = uuid.uuid4(), uuid.uuid4()
    page = Page(application_id=app_id, discovery_run_id=run_id, url="https://app/#/FindMyPolicy")
    screen = ExplorerScreen(
        run_id=uuid.uuid4(),
        signature="s",
        name="Claim policy lookup",
        view_kind="wizard",
        url=page.url,
        fields=[
            {"label": "Date of birth", "type": "date", "required": True},
            {"label": "Claim type", "type": "select", "required": False},
        ],
        actions=[
            {"label": "Find my policy", "kind": "submit"},
            {"label": "Return to Home", "kind": "navigate"},
            {"label": "Icon", "kind": "other"},
        ],
    )
    session = _Collect()
    _persist_screen_model(session, app_id, run_id, page, screen)  # type: ignore[arg-type]

    (form,) = [r for r in session.rows if isinstance(r, Form)]
    assert form.page_id == page.id and form.discovery_run_id == run_id
    fields = {f.name: f for f in session.rows if isinstance(f, FormField)}
    assert fields["Date of birth"].input_type == "date" and fields["Date of birth"].required
    assert fields["Claim type"].captured_selector == 'get_by_role("combobox", name="Claim type")'
    components = {c.name: c for c in session.rows if isinstance(c, Component)}
    assert set(components) == {"Date of birth", "Claim type", "Find my policy", "Return to Home"}
    assert components["Return to Home"].type == "link"
    assert components["Find my policy"].action == "click"
    preferred = {
        loc.value
        for loc in session.rows
        if isinstance(loc, ComponentLocator) and loc.kind == "preferred"
    }
    assert 'get_by_role("button", name="Find my policy")' in preferred


def test_route_steps_show_the_whole_route_in_plain_words() -> None:
    from explorer_worker.promote import route_steps

    steps = route_steps(
        [
            {"do": "goto", "url": "https://app/#/FindMyPolicy"},
            {"do": "fill", "field": "Policy number", "value": "POL-10001"},
            {"do": "fill", "field": "Password", "value": "{{password}}"},
            {"do": "click", "label": "Find my policy"},
            {"do": "click", "label": "Start over instead", "optional": True},
            {"do": "choose", "field": "What kind of claim is this?", "option": "Auto collision"},
            {"do": "upload", "field": "Photos", "kind": "image"},
            {"do": "click", "label": "Send my report"},
        ]
    )
    assert steps == [
        "Open https://app/#/FindMyPolicy",
        "Enter “POL-10001” in “Policy number”",
        "Enter the saved password in “Password”",  # never the secret
        "Press “Find my policy”",
        "If it's shown: press “Start over instead”",
        "Choose “Auto collision” for “What kind of claim is this?”",
        "Attach a sample image file to “Photos”",
        "Press “Send my report”",
    ]
    assert route_steps(None) == []  # nothing recorded: the planned steps are used


def test_captured_flow_uses_the_recorded_locator() -> None:
    flow = captured_flow(
        [
            {"do": "goto", "url": "https://app/#/start"},
            {"do": "fill", "field": "Name", "value": "Ada",
             "locator": {"by": "placeholder", "text": "Enter full name"}},
            {"do": "choose", "field": "Kind", "option": "Rear",
             "locator": {"by": "label", "text": "Rear", "exact": True}},
            {"do": "click", "label": "Continue"},  # nothing recorded: the old way
        ]
    )
    assert flow[1]["value"] == 'get_by_placeholder("Enter full name")'
    assert flow[2]["value"] == 'get_by_label("Rear", exact=True)'
    assert flow[3]["value"] == 'get_by_role("button", name="Continue")'


def test_saved_credential_fills_are_marked_login_test_data() -> None:
    data = _test_data(
        [
            {"do": "fill", "field": "Username", "value": "{{username}}"},
            {"do": "fill", "field": "Password", "value": "{{password}}"},
            {"do": "click", "target": "Sign in"},
            {"do": "fill", "field": "Search", "value": "invoices"},
        ]
    )
    assert [(f["name"], f.get("login")) for f in data] == [
        ("Username", True),
        ("Password", True),
        ("Search", None),
    ]
