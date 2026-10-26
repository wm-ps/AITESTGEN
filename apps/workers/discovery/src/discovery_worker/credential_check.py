"""Pre-discovery login check — "do these credentials actually sign in?".

Runs a real Playwright login (same `standard_login` shape discovery itself
uses) against the Application's Login URL, or else its Deployed URL following
a login link, and judges the outcome. Deliberately a separate module from
`session.py`: `establish_session` persists the login page/form via
`on_capture` (wrong before an Application row exists) and `attempt_login`
swallows every failure by design, so neither can report a verdict. This only
*calls* `attempt_login` unchanged (fill + submit) and reads the page
afterwards — nothing the crawler or mid-crawl re-login depends on is touched.

Three outcomes, never claiming "invalid" unless the app itself said so:
- `valid`: the password field stayed gone, with no credential-error text.
- `invalid`: the login form is still showing *and* the app rendered a visible
  invalid-credentials message.
- `uncertain`: everything else (slow app, no login form found, unrecognised
  wording, unchanged page) — the user is asked to validate again.
"""

import asyncio
import re
from collections.abc import Callable

from playwright.async_api import Browser
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from workflows import VerifyCredentialsResult

from discovery_worker.session import (
    _LOGIN_HREF_SELECTOR,
    _LOGIN_LINK_RE,
    _VIEWPORT,
    attempt_login,
)

# ponytail: fixed windows/attempt counts, not configurable. The worst case
# (2x20s goto + 15s form wait + 5s link click + _SETTLE_SECONDS) is what
# VerifyCredentialsWorkflow's activity timeouts are sized from — change them
# together.
_GOTO_ATTEMPTS = 2
_GOTO_TIMEOUT_MS = 20000
_FORM_WAIT_MS = 15000
_LINK_NAV_TIMEOUT_MS = 5000
_SETTLE_SECONDS = 60
_POLL_SECONDS = 0.5
# A failed login that reloads the page makes the password field vanish for a
# moment before reappearing — one or two absent ticks isn't proof of success.
_VALID_STABLE_TICKS = 3

_PASSWORD_SELECTOR = 'input[type="password"]'

# ponytail: English-only wording match over a fixed list of common error
# containers — an app that words its rejection differently (or localises it)
# lands in `uncertain` rather than `invalid`. A fuller version would need
# per-app configurable selectors/phrases.
_ERROR_SELECTORS = (
    '[role="alert"], .error, .errors, .error-message, .invalid-feedback, '
    ".alert-danger, .alert-error, mat-error, .mat-mdc-form-field-error, "
    '#input-error, .kc-feedback-text, [class*="error" i]'
)
_INVALID_CREDENTIALS_RE = re.compile(
    r"invalid|incorrect|bad credentials|wrong (?:user|pass|email|credential)"
    r"|unauthori[sz]ed|not (?:valid|match|correct|recogni[sz]ed)|do(?:es)?n'?t match"
    r"|(?:login|log in|sign[- ]?in|authentication) (?:failed|unsuccessful)|access denied",
    re.IGNORECASE,
)
# Containers wider than a message (a page wrapper whose class merely contains
# "error") must not count as the app's rejection text.
_MAX_ERROR_TEXT_LENGTH = 300

_PAGE_STATE_JS = """
([passwordSelector, errorSelector, maxLength]) => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  return {
    passwordVisible: Array.from(document.querySelectorAll(passwordSelector)).some(visible),
    errors: Array.from(document.querySelectorAll(errorSelector))
      .filter(visible)
      .map((el) => (el.innerText || '').trim())
      .filter((t) => t && t.length <= maxLength),
  };
}
"""


def _uncertain(detail: str) -> VerifyCredentialsResult:
    return VerifyCredentialsResult(status="uncertain", detail=detail)


async def _read_page_state(page) -> tuple[bool, str | None]:
    state = await page.evaluate(
        _PAGE_STATE_JS, [_PASSWORD_SELECTOR, _ERROR_SELECTORS, _MAX_ERROR_TEXT_LENGTH]
    )
    matched = next(
        (text for text in state["errors"] if _INVALID_CREDENTIALS_RE.search(text)), None
    )
    return state["passwordVisible"], matched


async def verify_login(
    browser: Browser,
    *,
    credential: bytes,
    base_url: str,
    login_url: str | None = None,
    heartbeat: Callable[[], None] | None = None,
) -> VerifyCredentialsResult:
    """`credential` is the same `{"username", "password"}` JSON bytes
    `attempt_login` takes. Always closes its own browser context."""
    context = await browser.new_context(viewport=_VIEWPORT)
    try:
        page = await context.new_page()
        if heartbeat:
            heartbeat()

        loaded = False
        for _ in range(_GOTO_ATTEMPTS):
            try:
                await page.goto(login_url or base_url, timeout=_GOTO_TIMEOUT_MS)
                loaded = True
                break
            except PlaywrightTimeoutError:
                if heartbeat:
                    heartbeat()
            except Exception:  # noqa: BLE001 — a load failure is "couldn't check", not "invalid"
                break
        if not loaded:
            return _uncertain("The login page did not load.")

        # Same wait discovery uses: rides out an SPA's delayed redirect to an
        # identity provider before concluding there's no login form.
        try:
            await page.wait_for_selector(_PASSWORD_SELECTOR, timeout=_FORM_WAIT_MS)
        except Exception:  # noqa: BLE001
            pass
        if heartbeat:
            heartbeat()

        password_input = page.locator(_PASSWORD_SELECTOR).first
        if await password_input.count() == 0:
            login_link = page.get_by_role("link", name=_LOGIN_LINK_RE).first
            if await login_link.count() == 0:
                login_link = page.locator(_LOGIN_HREF_SELECTOR).first
            if await login_link.count() > 0:
                try:
                    async with page.expect_navigation(timeout=_LINK_NAV_TIMEOUT_MS):
                        await login_link.click()
                except Exception:  # noqa: BLE001
                    pass
                if heartbeat:
                    heartbeat()
                password_input = page.locator(_PASSWORD_SELECTOR).first
        if await password_input.count() == 0:
            return _uncertain("Could not find a login form.")

        try:
            await attempt_login(page, credential, heartbeat=heartbeat)
        except Exception:  # noqa: BLE001 — e.g. no fillable field: can't tell either way
            return _uncertain("Could not fill in the login form.")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + _SETTLE_SECONDS
        absent_ticks = 0
        while loop.time() < deadline:
            if heartbeat:
                heartbeat()
            try:
                password_visible, error_text = await _read_page_state(page)
            except Exception:  # noqa: BLE001 — page mid-navigation; the next tick re-reads it
                await asyncio.sleep(_POLL_SECONDS)
                continue

            if password_visible and error_text:
                return VerifyCredentialsResult(status="invalid", detail=error_text)
            if not password_visible and not error_text:
                absent_ticks += 1
                if absent_ticks >= _VALID_STABLE_TICKS:
                    return VerifyCredentialsResult(status="valid")
            else:
                absent_ticks = 0
            await asyncio.sleep(_POLL_SECONDS)

        return _uncertain("The login result could not be confirmed.")
    finally:
        await context.close()


__all__ = ["verify_login"]
