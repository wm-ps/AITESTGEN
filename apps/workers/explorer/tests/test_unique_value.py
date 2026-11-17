"""`{{unique}}`: a record a test creates gets a new name on every run (a
replay never saves a duplicate the app refuses), the same all through one
run so the test can find it again — in Explorer and in the exported test."""

from explorer_worker.browser import Eyes
from explorer_worker.sense import resolve_relative
from explorer_worker.testkit import holds, playwright_code

PAGE = """<label for="n">Account Name</label><input id="n">
<button onclick="document.getElementById('out').textContent = document.getElementById('n').value">
Save</button><p id="out"></p>"""


def test_the_token_is_this_runs_stamp() -> None:
    assert resolve_relative("Acme {{unique}}", unique="a1b2c3") == "Acme a1b2c3"
    assert resolve_relative("Acme {{ UNIQUE }}") != "Acme {{ UNIQUE }}"


async def test_a_created_name_is_new_each_run_and_found_again() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        eyes.mark_calls()
        first = eyes.unique
        await eyes.fill_field("Account Name", "Acme {{unique}}")
        await eyes.page.click("text=Save")
        check = {"kind": "text_visible", "value": "Acme {{unique}}"}
        assert await eyes.page.input_value("#n") == f"Acme {first}"
        assert await holds(eyes, check, wait_ms=2000)
        eyes.mark_calls()  # the next run (a replay) makes its own
        assert eyes.unique != first
    finally:
        await eyes.close()
    fill = {
        "do": "fill",
        "field": "Account Name",
        "value": "Acme {{unique}}",
        "locator": {"by": "label", "text": "Account Name"},
    }
    code = playwright_code("Save an account", [], [fill], check, "x")
    assert "const UNIQUE = " in code
    assert 'getByText(rel("Acme {{unique}}"))' in code
    assert '.first()), rel("Acme {{unique}}"));' in code  # the fill, too
