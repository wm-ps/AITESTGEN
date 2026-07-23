"""Establishing a browser session before crawling (Story 2.2, Task 3).

Two shapes, matching Story 1.4's Authentication method select:
- `standard_login`: navigate to the Application and drive whatever login
  form is there (heuristic: the page with a password input), the same
  "sound, non-binding default" latitude Task 3 gives the crawl algorithm
  itself — FR-3 doesn't fix an exact login-form shape.
- `sso_session_reuse`: the resolved secret already *is* a Playwright
  `storageState`-shaped JSON blob (Story 1.4's placeholder mechanism) —
  reuse it directly via `new_context(storage_state=...)`, no login step.

`[FIXED 2026-07-22]` The base URL itself is very often a marketing/landing
page with no password field at all — the actual login form lives behind a
"Log in"/"Sign in" link (observed live: shopbit.onwavemaker.com's `/` has no
`input[type=password]`, only a link to `/login`). The old code gave up the
instant the landing page itself lacked one, silently returning an
unauthenticated context — every authenticated page (Order History, Product
Management, ...) then looked identical to an anonymous visitor and was never
reachable at all. Now follows one such link first, if present, before
giving up.

`[FIXED 2026-07-22, again]` The first fix only matched a login link by its
*visible text* ("Log in"/"Sign in"). shopbit's real link is icon-only —
`<a href="login"><span class="icon icon-person"></span></a>`, no text, no
aria-label — so it has no accessible name at all and the text-based match
still found nothing, silently reproducing the exact same "crawls
unauthenticated" bug one level deeper. Now also tries matching by `href`
(login/signin/sign-in), which an icon-only link still carries.

`[FIXED 2026-07-22, a third time]` Both fixes above assumed a password field
(or a link to one) exists on the page the instant `goto()` resolves. A
client-rendered SPA can take several seconds *after* that to redirect
through an external OAuth/OIDC identity provider — observed live: a Next.js
app (poc-react-app.onwavemaker.com) hydrates, then redirects cross-origin to
a Keycloak-hosted login page ~4s later, well after `goto()`'s own "load"
event already fired on the pre-redirect shell (an empty `<body>`, no
password field, no login link at all yet — there's nothing to click,
nothing to wait for locally). Checking once immediately after `goto()`
caught this app in that empty in-between state and gave up. Now waits
(bounded, non-fatal on timeout) for a password field to actually show up —
this transparently rides out any same-page redirect chain, cross-origin or
not, since Playwright keeps waiting against whatever page this tab lands on.

`[ADDED 2026-07-22]` `attempt_login` is the credential-filling half of
`standard_login`, factored out so `crawler.py` can replay it mid-crawl. A
Keycloak-backed app can issue a very short-lived access token that expires
well before an exhaustive crawl finishes — observed live: a real crawl hit
zero actions, zero transitions, then landed straight back on the Keycloak
login screen a few requests into a normal run. Story 2.4 (AD-11) originally
treated any mid-crawl session expiry as terminal ("re-authenticate to
continue") — reasonable for a normal, long-lived session cookie, but for a
token this short-lived that just means the crawl can *never* finish. The
crawler now replays this same login step in place and keeps going, bounded
by a small retry cap (see `crawler.py`) so a genuinely broken login doesn't
spin forever.

`[FIXED 2026-07-22, again]` Neither `establish_session` nor `attempt_login`
ever called `heartbeat()` — the exact bug crawler.py's own module docstring
already documents fixing elsewhere (2026-07-20: "heartbeat() was only ever
called once per page... a slow page caused no heartbeat for >120s, Temporal
declared the activity heartbeat-timed-out, and retried DiscoveryActivity
from scratch"). A real cross-origin OAuth login round-trip (observed live:
several seconds, sometimes longer) is exactly this class of risk, and with a
short-lived token this replay can happen *often* mid-crawl — every single
occurrence risked the whole Activity being silently killed and retried from
absolute zero by Temporal (invisible to this code: no exception, no
`discovery_run.status` change, just `stage` regressing back to
"authenticating" as a fresh attempt starts over), discarding all in-memory
BFS/checkpoint state every time. Heartbeats now bracket every real wait here
too, not just in the main crawl loop.
"""

import asyncio
import json
import re
import uuid
from collections.abc import Callable
from typing import Any

from playwright.async_api import Browser, BrowserContext
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

_LOGIN_LINK_RE = re.compile(r"log\s*in|sign\s*in", re.IGNORECASE)
_LOGIN_HREF_SELECTOR = (
    "a[href*='login' i], a[href*='signin' i], a[href*='sign-in' i]"
)

# `[FIXED 2026-07-22]` Playwright's own default viewport (1280x720) is
# narrow enough to trip a real app's responsive breakpoint — observed live:
# a Material-UI admin dashboard's entire left-nav sidebar rendered present in
# the DOM (readable via `.inner_text()`) but not *visible* (Playwright's
# click actionability check failed on every single item, "element is not
# visible", never a selector problem). A generous, unambiguously-desktop
# viewport is what "navigates the way a thorough tester would" (FR-6)
# actually implies — nobody testing a back-office admin app does it in a
# viewport barely wider than a tablet.
_VIEWPORT = {"width": 1920, "height": 1080}


async def establish_session(
    browser: Browser,
    *,
    auth_method: str,
    credential: bytes,
    base_url: str,
    heartbeat: Callable[[], None] | None = None,
    object_store: Any = None,
    discovery_run_id: uuid.UUID | None = None,
    on_capture: Callable[[Any], None] | None = None,
) -> BrowserContext:
    if auth_method == "sso_session_reuse":
        storage_state = json.loads(credential.decode())
        return await browser.new_context(storage_state=storage_state, viewport=_VIEWPORT)

    context = await browser.new_context(viewport=_VIEWPORT)
    page = await context.new_page()
    if heartbeat:
        heartbeat()
    # `[FIXED 2026-07-22]` A real target's very first request can be slow
    # (cold start, CDN warmup) — observed live, repeatedly, against a real
    # app: Playwright's 30s default timeout got hit on the initial `goto()`
    # before the app ever responded, failing the whole Discovery Run at the
    # "authenticating" stage before a single request past the first even had
    # a chance.
    #
    # `[FIXED 2026-07-22, again]` The first fix (one retry at 60s each, up to
    # 120s total) collided with `DiscoveryActivity`'s own 2-minute
    # `heartbeat_timeout` — a single `await` can't heartbeat *during* itself,
    # only between awaits, so two consecutive 60s-timeout attempts can burn
    # the entire heartbeat budget with zero chance to check in, and Temporal
    # kills and retries the whole Activity from scratch regardless of how
    # many `heartbeat()` calls exist elsewhere in this file. More attempts at
    # a shorter timeout each, heartbeating between every one, keeps the
    # worst case well under that ceiling while still tolerating the same
    # real-world slow-first-request case.
    for attempt in range(4):
        try:
            await page.goto(base_url, timeout=20000)
            break
        except PlaywrightTimeoutError:
            if heartbeat:
                heartbeat()
            if attempt == 3:
                raise
    if heartbeat:
        heartbeat()
    try:
        await page.wait_for_selector('input[type="password"]', timeout=15000)
    except Exception:
        pass
    if heartbeat:
        heartbeat()

    password_input = page.locator('input[type="password"]').first
    if await password_input.count() == 0:
        login_link = page.get_by_role("link", name=_LOGIN_LINK_RE).first
        if await login_link.count() == 0:
            login_link = page.locator(_LOGIN_HREF_SELECTOR).first
        if await login_link.count() > 0:
            try:
                async with page.expect_navigation(timeout=5000):
                    await login_link.click()
            except Exception:
                pass
            if heartbeat:
                heartbeat()
            password_input = page.locator('input[type="password"]').first
    if await password_input.count() == 0:
        await page.close()
        return context

    # `[ADDED 2026-07-23]` The login form/page itself was structurally
    # invisible to every downstream Page/Form/Journey — `run_discovery_crawl`
    # only starts *after* this function returns, on an already-authenticated
    # context, so nothing about the sign-in step was ever captured and no
    # "Sign in" journey could ever be inferred from it. Captured once, right
    # here, before the one-time initial login (never during `attempt_login`'s
    # other caller — `crawler.py`'s mid-crawl session-expiry replay — which
    # would otherwise re-capture the same login page/form on every re-auth).
    if object_store is not None and discovery_run_id is not None and on_capture is not None:
        try:
            from discovery_worker.crawler import (
                CapturedForm,
                CapturedFormField,
                CapturedPage,
                _capture_selector,
                _generic_value,
            )

            login_url = page.url
            screenshot = await page.screenshot()
            title = await page.title()
            key = await asyncio.to_thread(object_store.put, screenshot, discovery_run_id)
            await asyncio.to_thread(
                on_capture, CapturedPage(url=login_url, title=title, object_storage_key=key)
            )

            fields: list[CapturedFormField] = []
            username_input = page.locator(
                'input[type="email"], input[name*="user" i], input[type="text"]'
            ).first
            if await username_input.count() > 0:
                name = await username_input.get_attribute("name")
                input_type = await username_input.get_attribute("type") or "text"
                field_id = await username_input.get_attribute("id")
                fields.append(
                    CapturedFormField(
                        name=name,
                        input_type=input_type,
                        required=await username_input.get_attribute("required") is not None,
                        default_value=_generic_value(input_type, name, field_id),
                        captured_selector=await _capture_selector(
                            username_input, fallback_text=name
                        ),
                    )
                )
            password_name = await password_input.get_attribute("name")
            fields.append(
                CapturedFormField(
                    name=password_name,
                    input_type="password",
                    required=True,
                    default_value=_generic_value(
                        "password", password_name, await password_input.get_attribute("id")
                    ),
                    captured_selector=await _capture_selector(
                        password_input, fallback_text=password_name
                    ),
                )
            )
            await asyncio.to_thread(
                on_capture,
                CapturedForm(
                    page_url=login_url, action_url=login_url, method="POST", fields=fields
                ),
            )
        except Exception:
            # Best-effort — a capture hiccup here must never block the
            # actual login this whole crawl depends on.
            pass

    await attempt_login(page, credential, heartbeat=heartbeat)

    await page.close()
    return context


async def attempt_login(
    page, credential: bytes, *, heartbeat: Callable[[], None] | None = None
) -> None:
    """Fills and submits whatever login form is currently on `page` —
    requires a `input[type=password]` to already be present/visible (the
    caller is responsible for getting there, e.g. `establish_session`'s own
    link-following above, or simply having landed back on it via a mid-crawl
    session-expiry redirect). Best-effort, like every other settle step in
    this module: a failed submit just leaves the caller to notice the page
    never became authenticated, rather than raising here."""
    if heartbeat:
        heartbeat()
    creds = json.loads(credential.decode())
    username_input = page.locator(
        'input[type="email"], input[name*="user" i], input[type="text"]'
    ).first
    if await username_input.count() > 0:
        await username_input.fill(creds["username"])
    password_input = page.locator('input[type="password"]').first
    await password_input.fill(creds["password"])
    if heartbeat:
        heartbeat()

    submit = page.locator('button[type="submit"], input[type="submit"]').first
    try:
        if await submit.count() > 0:
            async with page.expect_navigation(timeout=5000):
                await submit.click()
        else:
            await password_input.press("Enter")
    except Exception:
        pass
    if heartbeat:
        heartbeat()
