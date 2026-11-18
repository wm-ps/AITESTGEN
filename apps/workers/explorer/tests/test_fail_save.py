"""A failed save, made on purpose (F-20): the app's next save gets a server
error, once — in Explorer and in the exported test alike."""

from explorer_worker.browser import Eyes
from explorer_worker.testkit import playwright_code, without_decisive_step

PAGE = """<button onclick="fetch('https://app.test/api/accounts', {method: 'POST'})
  .then(r => out.textContent += ' saved:' + r.status, () => out.textContent += ' offline')">
Save</button><p id="out"></p>"""


async def test_the_next_save_fails_once() -> None:
    eyes = Eyes("about:blank")
    await eyes.open()
    try:
        assert eyes.page is not None
        await eyes.page.set_content(PAGE)
        assert await eyes.browser("fail_next_save")
        await eyes.page.click("text=Save")
        await eyes.page.wait_for_function("out.textContent.includes('saved:500')")
        await eyes.page.click("text=Save")  # only once: the next save is the app's own
        await eyes.page.wait_for_function("out.textContent.split(' ').length > 2")
        assert (await eyes.page.text_content("#out") or "").split()[1] != "saved:500"
    finally:
        await eyes.close()


def test_the_failed_save_is_exported_and_never_the_step_dropped() -> None:
    script = [
        {"do": "fail_next_save"},
        {
            "do": "click",
            "label": "Save",
            "locator": {"by": "role", "role": "button", "name": "Save"},
        },
    ]
    code = playwright_code("A failed save keeps the data", [], script, None, "x")
    assert "route.fulfill({ status: 500" in code and "used = true" in code
    # The deliberately broken run drops the Save press, not the failure set-up.
    assert without_decisive_step(script) == [{"do": "fail_next_save"}]
