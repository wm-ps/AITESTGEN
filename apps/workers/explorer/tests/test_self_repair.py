"""Explorer repairs a step that didn't take effect on its own, at run time,
whatever the widget: it reads the page back, asks what is really going on,
does what the page needs, checks it worked, records it as ordinary steps
(replayed and exported the same way) and remembers the lesson for the app.
The model is a stub here; the page and the browser are real."""

import uuid
from typing import Any

import pytest
from explorer_worker import brain, repair
from explorer_worker.browser import Eyes, element_spec
from explorer_worker.testkit import playwright_code, replay
from explorer_worker.tests_stage import was_there

# A date box that only keeps its value once Enter confirms it (until then the
# app flags it), and an Export hidden in a "More" menu.
PAGE = """
<label for="d">Close Date</label>
<input id="d" placeholder="dd/mm/yyyy"
  oninput="this.setAttribute('aria-invalid','true')"
  onkeydown="if (event.key === 'Enter') this.setAttribute('aria-invalid','false')">
<button onclick="document.getElementById('menu').hidden = false">More</button>
<div id="menu" role="menu" hidden>
  <div role="menuitem" tabindex="0" onclick="document.body.append('Exported')">Export</div>
</div>
"""


class _Journal:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.run_id = uuid.uuid4()  # no saved pages: the live check alone

    def event(self, kind: str, title: str, detail: Any = None, *_: Any) -> None:
        self.events.append((title, str(detail or "")))


def _answers(monkeypatch: pytest.MonkeyPatch, *replies: dict[str, Any]) -> list[dict[str, Any]]:
    asked: list[dict[str, Any]] = []
    queue = list(replies)

    async def repair_step(goal: str, intent: str, problem: str, elements: str, *_a: Any) -> Any:
        asked.append({"intent": intent, "problem": problem, "elements": elements})
        reply = queue.pop(0)
        reply.setdefault("actions", [])
        return reply

    monkeypatch.setattr(brain, "repair_step", repair_step)
    return asked


def test_an_element_line_from_the_page_becomes_a_locator() -> None:
    assert element_spec('textbox "Close Date"') == {
        "by": "role",
        "role": "textbox",
        "name": "Close Date",
        "exact": True,
    }
    assert element_spec('- option "Won" [selected]')["role"] == "option"  # type: ignore[index]
    assert element_spec("text: Saved") == {"by": "text", "text": "Saved", "exact": True}
    assert element_spec("something vague") is None


async def test_a_value_the_app_did_not_keep_is_repaired_and_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _answers(
        monkeypatch,
        {
            "diagnosis": "The date box only keeps a date once Enter confirms it.",
            "actions": [
                {"do": "type", "target": 'textbox "Close Date"', "text": "18/12/2026"},
                {"do": "key", "key": "Enter", "target": 'textbox "Close Date"'},
            ],
            "lesson": "Close Date needs Enter to keep a date",
        },
    )
    eyes, journal = Eyes("about:blank"), _Journal()
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        # Typed in the format the field states — and the app still flags it.
        assert await eyes.fill_field("Close Date", "2026-12-18")
        assert await eyes.page.locator("#d").input_value() == "18/12/2026"
        assert eyes.last_date_format == "dd/mm/yyyy"
        check = repair.fill_check(eyes, eyes.last_locator, "2026-12-18")
        kept, shows = await check([])
        assert not kept and "flags it" in shows
        fixed, steps = await repair.fix(
            eyes, journal, "Save an opportunity", "enter a date in Close Date", shows, check
        )
        assert fixed
        assert [s["do"] for s in steps] == ["fill", "key"]
        assert "flags it" in asked[0]["problem"] and 'textbox "Close Date"' in asked[0]["elements"]
        assert "Close Date needs Enter to keep a date" in repair.lessons(eyes.origin)
        # What fixed it replays, and exports, the same way.
        await eyes.page.set_content(PAGE)
        assert await replay(eyes, steps)
        assert await eyes.page.locator("#d").get_attribute("aria-invalid") == "false"
        script = [{"do": "goto", "url": "https://a/"}, *steps]
        code = playwright_code("t", [], script, None, "e", None)
        assert "page.keyboard.press('Enter')" in code or 'page.keyboard.press("Enter")' in code
    finally:
        await eyes.close()


async def test_a_press_that_found_nothing_is_repaired_from_the_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answers(
        monkeypatch,
        {
            "diagnosis": "Export sits in the More menu.",
            "actions": [
                {"do": "click", "target": 'button "More"'},
                {"do": "click", "target": 'menuitem "Export"'},
            ],
        },
    )
    eyes, journal = Eyes("about:blank"), _Journal()
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        before = await eyes.fingerprint()
        assert not await eyes.click_text("Export", "button")
        fixed, steps = await repair.fix(
            eyes,
            journal,
            "Export the list",
            "press “Export”",
            eyes.last_press_problem or "",
            repair.press_check(eyes, before),
        )
        assert fixed and [s["label"] for s in steps] == ["More", "Export"]
        assert "Exported" in await eyes.page.inner_text("body")
    finally:
        await eyes.close()


async def test_a_value_refused_on_purpose_or_a_real_bug_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answers(
        monkeypatch,
        {"give_up": "intended"},
        {"give_up": "The server fails every save: a bug in the app, not to work around."},
    )
    eyes, journal = Eyes("about:blank"), _Journal()
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)

        async def never(_steps: list[dict[str, Any]]) -> tuple[bool, str]:
            return False, "flagged"

        assert await repair.fix(eyes, journal, "g", "enter -1", "flagged", never) == (False, [])
        assert journal.events == []  # the refusal is the point: nothing to say
        assert await repair.fix(eyes, journal, "g", "save", "error", never) == (False, [])
        assert journal.events[-1][0] == "Left as it is: save"
    finally:
        await eyes.close()


def test_what_the_tests_own_last_action_changed_is_its_proof() -> None:
    empty = '- combobox "Account"'
    filled = '- combobox "Account": Harborview Industrial Supply Ltd'
    proof = {"kind": "element_state", "value": empty}
    # The form opened with Account empty; the test filled it, then pressed Clear.
    assert not was_there(proof, "", "", None, empty, ("", filled))
    # Without what the screen showed before the last action, it looks unchanged.
    assert was_there(proof, "", "", None, empty, None)
    # A label shown the whole time stays no proof.
    label = {"kind": "text_visible", "value": "Account"}
    assert was_there(label, "Account", "", None, empty, ("Account", filled))
