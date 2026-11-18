"""Explorer carrying out a planned step on any app, not one app's quirks: a
press waits for a screen still drawing, finds the control however its name
was written, reuses what pressed it before and gets past a covered element; a
proven route survives one miss; a scenario that never reached its screen is
tried again later; a control's own name is never a proof; a field flagged by
error styling counts; and uploads can test "how many" and "how big" limits."""

import re
import uuid
from typing import Any

import pytest
from explorer_worker import missions
from explorer_worker.browser import PRESS_WAIT_MS, Eyes, plain_name, press_specs
from explorer_worker.samples import sample_file, sample_files, upload_shape
from explorer_worker.testkit import FIELD_FLAGGED_JS, names_a_control, playwright_code
from explorer_worker.tests_stage import try_order

# The toolbar draws a moment after the page, as single-page apps do.
LATE_BUTTON = """
<div id="bar"></div>
<script>
  setTimeout(() => {
    const b = document.createElement('button');
    b.innerHTML = '<svg width="8" height="8"></svg> New Lead';
    b.onclick = () => { document.body.dataset.pressed = 'new'; };
    document.getElementById('bar').append(b);
  }, 1500);
</script>
<button aria-label="Close dialog" onclick="document.body.dataset.pressed='close'">×</button>
<div style="position:relative">
  <button id="under" onclick="document.body.dataset.pressed='under'">Covered</button>
  <div id="veil" style="position:absolute;inset:0;background:#fff"></div>
</div>
"""


def test_a_name_is_read_the_way_the_page_writes_it() -> None:
    assert plain_name("+ New Lead") == "New Lead"
    assert plain_name("New Lead button") == "New Lead"
    assert plain_name("“Save” ›") == "Save"
    assert plain_name("Why?") == "Why?"
    specs = press_specs("+ New Lead", "button", None, None)
    # Exact names first (as written, then plain), loose ones after.
    assert specs[0] == {"by": "role", "role": "button", "name": "+ New Lead", "exact": True}
    assert {"by": "role", "role": "button", "name": "New Lead", "exact": True} in specs
    assert specs[-1]["by"] == "css" and "aria-label" in specs[-1]["selector"]
    learned = {"by": "css", "selector": "#x"}
    assert press_specs("Go", None, None, learned)[0] == learned  # what worked before, first


async def test_a_press_waits_finds_and_gets_past_what_is_in_the_way() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        page = eyes.page
        assert page is not None
        await page.set_content(LATE_BUTTON)
        # One look (probing): not drawn yet, nothing pressed, and it says why.
        assert not await eyes.click_text("New Lead", "button")
        assert eyes.last_press_problem == "nothing named “New Lead” to press on this screen"
        # A real press waits for it, and finds it as the model wrote it.
        assert await eyes.click_text("+ New Lead", "button", wait_ms=PRESS_WAIT_MS)
        assert await page.evaluate("document.body.dataset.pressed") == "new"
        # Named only by aria-label: still found.
        assert await eyes.click_text("Close dialog button", "button")
        assert await page.evaluate("document.body.dataset.pressed") == "close"
        # Covered by another element: keyboard Enter presses it.
        assert await eyes.click_text("Covered", "button")
        assert await page.evaluate("document.body.dataset.pressed") == "under"
    finally:
        await eyes.close()


@pytest.mark.parametrize(
    ("html", "flagged"),
    [
        ('<input id="f" class="form-control is-invalid">', True),
        ('<div class="form-group has-error"><input id="f"></div>', True),
        ('<div class="MuiInputBase-root Mui-error"><input id="f"></div>', True),
        ('<input id="f" class="ng-invalid ng-touched">', True),
        ('<input id="f" aria-invalid="true">', True),
        # Not yet touched by the user, or only the whole form: not this field.
        ('<input id="f" class="ng-invalid ng-untouched ng-pristine">', False),
        ('<form class="invalid"><input id="f"></form>', False),
        ('<input id="f" class="error-message-hint">', False),
    ],
)
async def test_a_field_flagged_by_error_styling_counts(html: str, flagged: bool) -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(html)
        assert await eyes.page.locator("#f").evaluate(FIELD_FLAGGED_JS) is flagged
    finally:
        await eyes.close()


def test_a_controls_own_name_is_never_the_proof() -> None:
    aria = (
        '- combobox "Lead Status*":\n- textbox "Last Name*"\n'
        '- button "Save Lead"\n- heading "New Lead"'
    )
    assert names_a_control({"kind": "text_visible", "value": "Lead Status"}, aria)
    assert names_a_control({"value": "Save Lead"}, aria)
    assert not names_a_control({"kind": "text_visible", "value": "New Lead"}, aria)  # a heading
    assert not names_a_control({"kind": "text_visible", "value": "Last Name is required"}, aria)
    assert not names_a_control({"kind": "field_invalid", "value": "Last Name"}, aria)


def test_uploads_can_test_how_many_and_how_big() -> None:
    assert upload_shape({}) == (1, None)
    assert upload_shape({"count": 6}) == (6, None)
    assert upload_shape({"count": 99, "size_mb": 999}) == (10, 50.0)  # within limits
    six = sample_files("pdf", 6)
    assert len({p.name for p in six}) == 6  # distinct names
    [big] = sample_files("pdf", 1, 11)
    assert big.stat().st_size == 11 * 1024 * 1024
    assert big.read_bytes().startswith(sample_file("pdf").read_bytes())  # still a PDF
    code = playwright_code(
        "More than five attachments are refused",
        [],
        [
            {"do": "goto", "url": "https://app/#/new"},
            {"do": "upload", "field": "Choose Files", "kind": "pdf", "count": 6},
            {"do": "upload", "field": "Choose Files", "kind": "pdf", "size_mb": 11},
        ],
        {"kind": "text_visible", "value": "You can attach up to 5 files"},
        "Refused",
        None,
    )
    assert len(re.findall(r"repair-estimate-\d\.pdf", code)) == 6  # six files in one call
    assert "repair-estimate-11mb.pdf" in code
    assert f"Buffer.alloc({11 * 1024 * 1024 - sample_file('pdf').stat().st_size})" in code


async def test_a_proven_route_survives_one_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    run, forgotten = uuid.uuid4(), []
    outcomes = [False, True, False, False]

    async def replay(*_a: Any) -> bool:
        return outcomes.pop(0)

    async def nothing(*_a: Any) -> None:
        return None

    monkeypatch.setattr(missions, "path_to", lambda *_a: [{"do": "goto", "url": "u"}, {}])
    monkeypatch.setattr(missions, "replay", replay)
    monkeypatch.setattr(missions, "forget_route", lambda r, s: forgotten.append(s))
    eyes = type("E", (), {"stop_starting_fresh": nothing, "goto": nothing})()
    journal = type("J", (), {"event": lambda *a: None})()
    for _ in range(4):
        await missions.fast_forward(eyes, journal, run, "New Lead")  # type: ignore[arg-type]
    # Miss, then it worked (count reset), then two misses in a row: forgotten once.
    assert forgotten == ["New Lead"]


def test_a_scenario_that_never_reached_its_screen_is_tried_after_the_others() -> None:
    planned = [
        ("a", "validation", "New Lead", [{"unreached": True}]),
        ("b", "data_load", "New Lead", [{}]),
        ("c", "navigation", "Lead list", []),
    ]
    assert try_order(planned) == ["b", "c", "a"]
