"""Establishing a browser session before crawling (Story 2.2, Task 3).

Two shapes, matching Story 1.4's Authentication method select:
- `standard_login`: navigate to the Application and drive whatever login
  form is there (heuristic: the page with a password input), the same
  "sound, non-binding default" latitude Task 3 gives the crawl algorithm
  itself — FR-3 doesn't fix an exact login-form shape.
- `sso_session_reuse`: the resolved secret already *is* a Playwright
  `storageState`-shaped JSON blob (Story 1.4's placeholder mechanism) —
  reuse it directly via `new_context(storage_state=...)`, no login step.
"""

import json

from playwright.async_api import Browser, BrowserContext


async def establish_session(
    browser: Browser, *, auth_method: str, credential: bytes, base_url: str
) -> BrowserContext:
    if auth_method == "sso_session_reuse":
        storage_state = json.loads(credential.decode())
        return await browser.new_context(storage_state=storage_state)

    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(base_url)

    password_input = page.locator('input[type="password"]').first
    if await password_input.count() == 0:
        await page.close()
        return context

    creds = json.loads(credential.decode())
    username_input = page.locator(
        'input[type="email"], input[name*="user" i], input[type="text"]'
    ).first
    if await username_input.count() > 0:
        await username_input.fill(creds["username"])
    await password_input.fill(creds["password"])

    submit = page.locator('button[type="submit"], input[type="submit"]').first
    try:
        if await submit.count() > 0:
            async with page.expect_navigation(timeout=5000):
                await submit.click()
        else:
            await password_input.press("Enter")
    except Exception:
        pass

    await page.close()
    return context
