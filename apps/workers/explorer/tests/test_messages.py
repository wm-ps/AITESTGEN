"""How an app says a field is wrong varies, and some of it never stays on
screen: a toast fades after a few seconds (Denali: "Last Name is required."
gone after ~5s, before Explorer read the screen), the browser's own "Please
fill out this field" bubble is never part of the page, and an alert() pop-up
was dismissed unseen. Explorer records them as they happen."""

from explorer_worker.browser import _INVENTORY_JS, Eyes
from explorer_worker.testkit import holds, seen_message

PAGE = """<!doctype html><html><body>
<form onsubmit="event.preventDefault()">
  <label for="last">Last Name</label><input id="last" required>
  <label for="code">Code <span class="required">*</span></label><input id="code">
  <button type="submit">Save</button>
</form>
<button id="toast" onclick="
  const t = document.createElement('div'); t.className = 'toast toast-error';
  t.innerHTML = '<div class=toast-message>Last Name is required.</div>';
  document.body.appendChild(t); setTimeout(() => t.remove(), 300);">Save Contact</button>
<button id="pop" onclick="alert('Please complete the form')">Pop</button>
</body></html>"""


async def test_fading_toasts_browser_prompts_and_pop_ups_are_recorded() -> None:
    eyes = Eyes("https://app.test/")
    await eyes.open()
    try:
        page = eyes.page
        assert page is not None
        await page.route(
            "https://app.test/form",
            lambda route: route.fulfill(content_type="text/html", body=PAGE),
        )
        await page.goto("https://app.test/form")
        eyes.mark_calls()

        await page.click("#toast")
        await page.wait_for_timeout(800)  # the toast is gone by now
        assert await page.locator(".toast").count() == 0
        assert "Last Name is required." in eyes.messages_since_mark()
        proof = {"kind": "text_visible", "value": "last name is required"}
        assert seen_message(proof, eyes.messages)

        await page.click("button[type=submit]")  # the browser refuses the empty field
        await page.wait_for_timeout(300)
        assert any(m.startswith("Last Name: ") for m in eyes.messages_since_mark())
        # Refused by the browser's own check, which focuses it: a proof.
        assert await holds(eyes, {"kind": "field_invalid", "value": "Last Name"}, 2000)
        assert not await holds(eyes, {"kind": "field_invalid", "value": "Code"}, 500)

        await page.click("#pop")
        await page.wait_for_timeout(300)
        assert "Browser pop-up: Please complete the form" in eyes.messages_since_mark()

        # "Code *" has no `required` attribute, only the marker in its label.
        fields = {f["label"]: f for f in (await page.evaluate(_INVENTORY_JS))["fields"]}
        assert fields["Code *"]["required"] is True
        assert fields["Last Name"]["required"] is True
    finally:
        await eyes.close()
