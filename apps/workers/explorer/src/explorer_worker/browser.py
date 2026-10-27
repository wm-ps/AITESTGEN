"""Explorer's eyes and hands: a thin Playwright layer that opens the app,
signs in, reads what's on screen, and notices health problems (crashes,
server errors, background errors, slow loads) while it goes."""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    ViewportSize,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from explorer_worker.sense import (
    CONTINUE_LIKE,
    RESUME_LABEL,
    START_FRESH,
    date_variants,
    looks_final,
    resolve_relative,
)

VIEWPORT = ViewportSize(width=1440, height=900)

# The app's own files that don't change between windows (scripts, styles,
# fonts, images), kept once per worker and served to every new window. Each
# window is still brand new — no cookies, storage or saved progress carried
# over, like an exported test's — it just doesn't download the same bundles
# again (measured: 12-15s per window cold, 1.5s warm). Pages and data calls
# always go to the app. ponytail: in-memory, capped; a deploy mid-run is
# picked up when an entry expires.
STATIC_KINDS = {"script", "stylesheet", "font", "image"}
STATIC_CACHE_SECONDS = 30 * 60
STATIC_CACHE_BYTES = 300 * 1024 * 1024
_STATIC: dict[str, tuple[float, int, dict[str, str], bytes]] = {}
# Describe the body as it was received; ours is already decoded.
_DROP_HEADERS = {"content-encoding", "content-length", "transfer-encoding"}


def cacheable(method: str, kind: str, status: int, headers: dict[str, str]) -> bool:
    return (
        method == "GET"
        and kind in STATIC_KINDS
        and status == 200
        and "no-store" not in headers.get("cache-control", "").lower()
    )


async def _serve_static(route: Any) -> None:
    request = route.request
    if request.method != "GET" or request.resource_type not in STATIC_KINDS:
        await route.continue_()
        return
    hit = _STATIC.get(request.url)
    if hit is not None and time.monotonic() - hit[0] < STATIC_CACHE_SECONDS:
        await route.fulfill(status=hit[1], headers=hit[2], body=hit[3])
        return
    try:
        response = await route.fetch()
        body = await response.body()
    except PlaywrightError:
        await route.continue_()  # let the browser load it (and fail) as usual
        return
    headers = {k: v for k, v in response.headers.items() if k.lower() not in _DROP_HEADERS}
    if cacheable(request.method, request.resource_type, response.status, response.headers):
        if sum(len(entry[3]) for entry in _STATIC.values()) + len(body) <= STATIC_CACHE_BYTES:
            _STATIC[request.url] = (time.monotonic(), response.status, headers, body)
    await route.fulfill(status=response.status, headers=headers, body=body)
SLOW_LOAD_MS = 6000

# Reads the screen in one round trip. Elements a user could navigate with
# that aren't plain <a href> links (menu items, tabs, JS-driven links) are
# collected separately as `nav_items` — single-page apps hide most of their
# navigation there.
# One step of picking a date in whatever calendar popup is open: "picked"
# (clicked the day), "moved" (stepped a month toward it) or "none" (no
# calendar on screen). Framework-agnostic: finds the popup by role/class
# words, reads the month name + year it shows, uses its arrow buttons (or its
# year grid for far dates) and day cells. ponytail: English month names only — add locales when a
# non-English app turns up.
_CALENDAR_JS = r"""
({year, month, day}) => {
  const MONTHS = ['january','february','march','april','may','june','july','august','september','october','november','december'];
  const visible = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const txt = (e) => (e.innerText || '').trim();
  const lower = (e) => txt(e).toLowerCase();
  const cellsOf = (root, test) => [...root.querySelectorAll('button, td, [role=gridcell], span, a')]
    .filter((e) => visible(e) && test(txt(e)));
  const isDay = (t) => /^[0-9]{1,2}$/.test(t);
  const isYear = (t) => /^(19|20)[0-9]{2}$/.test(t);
  const isMonth = (t) => MONTHS.some((m) => t.toLowerCase() === m || t.toLowerCase().replace('.', '') === m.slice(0, 3));
  const innermost = (cells) => cells.filter((e) => !cells.some((o) => o !== e && e.contains(o)));
  // Marked for a real mouse click by the caller: pickers listen on the
  // innermost element, and synthetic clicks are often ignored.
  const mark = (e, outcome) => {
    document.querySelectorAll('[data-explorer-pick]').forEach((x) => x.removeAttribute('data-explorer-pick'));
    e.setAttribute('data-explorer-pick', '1');
    return outcome;
  };
  // Month words matched with plain character classes, not backslash escapes
  // (escapes inside a JS string built from Python were silently mangled once).
  const monthAt = (t, m) => t.search(new RegExp('(^|[^a-z])(' + m + '|' + m.slice(0, 3) + ')([^a-z]|$)'));
  const yearIn = (t) => { const y = t.match(/(19|20)[0-9]{2}/); return y ? Number(y[0]) : null; };
  const view = (e) => {
    if (innermost(cellsOf(e, isDay)).length >= 28) return 'days';
    if (innermost(cellsOf(e, isMonth)).length >= 12) return 'months';
    if (innermost(cellsOf(e, isYear)).length >= 9) return 'years';
    return null;
  };
  const popups = [...document.querySelectorAll('[role=dialog], [role=grid], [role=application], [class*=picker], [class*=calendar], [class*=Picker], [class*=Calendar]')]
    .filter((e) => visible(e) && view(e) && yearIn(lower(e)) !== null);
  if (!popups.length) return 'none';
  const pop = popups.reduce((a, b) => (txt(b).length < txt(a).length ? b : a));
  const shown = view(pop);
  const text = lower(pop);
  const arrow = (forward) => {
    const want = forward ? /(next|forward|›|»|>|right)/i : /(prev|back|‹|«|<|left)/i;
    const buttons = [...pop.querySelectorAll('button, [role=button], a')].filter(visible);
    const named = buttons.find((b) => want.test([b.getAttribute('aria-label'), b.getAttribute('title'), b.innerText, String(b.className || '')].join(' ')));
    const bare = buttons.filter((b) => !txt(b));
    return named || (forward ? bare[bare.length - 1] : bare[0]);
  };
  // The header's year (or "Month Year") button zooms out to a year grid.
  const title = () => {
    const heads = [...pop.querySelectorAll('button, [role=button], a, th')].filter((e) => visible(e) && yearIn(lower(e)) !== null && txt(e).length < 30);
    return heads.find((e) => isYear(txt(e))) || heads[0];
  };
  if (shown === 'days') {
    let shownMonth = -1, idx = Infinity;
    MONTHS.forEach((m, i) => { const at = monthAt(text, m); if (at >= 0 && at < idx) { idx = at; shownMonth = i + 1; } });
    const shownYear = yearIn(text);
    if (shownMonth < 0 || shownYear === null) return 'none';
    const diff = (year - shownYear) * 12 + (month - shownMonth);
    if (diff === 0) {
      const off = /(other|outside|disabled|muted|adjacent|[^a-z]off[^a-z]|not-current|next-month|prev-month)/i;
      const cells = cellsOf(pop, (t) => t === String(day)).filter((e) => !off.test(' ' + String(e.className || '') + ' ')
        && e.getAttribute('aria-disabled') !== 'true' && !e.disabled);
      const name = MONTHS[month - 1];
      const labelled = cells.find((e) => {
        const l = (e.getAttribute('aria-label') || e.getAttribute('title') || '').toLowerCase();
        return l.includes(String(year)) && (l.includes(name) || l.includes(name.slice(0, 3)));
      });
      const inner = innermost(cells);
      const cell = (labelled && inner.find((e) => labelled.contains(e))) || labelled || inner[0];
      return cell ? mark(cell, 'pick') : 'none';
    }
    if (Math.abs(diff) > 12) { const t = title(); if (t) return mark(t, 'click'); }
    const a = arrow(diff > 0);
    return a ? mark(a, 'click') : 'none';
  }
  if (shown === 'months') {
    const shownYear = yearIn(text);
    if (shownYear === year) {
      const name = MONTHS[month - 1];
      const cell = innermost(cellsOf(pop, (t) => t.toLowerCase() === name || t.toLowerCase().replace('.', '') === name.slice(0, 3)))[0];
      return cell ? mark(cell, 'click') : 'none';
    }
    if (Math.abs(year - shownYear) > 1) { const t = title(); if (t) return mark(t, 'click'); }
    const a = arrow(year > shownYear);
    return a ? mark(a, 'click') : 'none';
  }
  const years = innermost(cellsOf(pop, isYear));
  const hit = years.find((e) => txt(e) === String(year));
  if (hit) return mark(hit, 'click');
  const a = arrow(year > Math.max(...years.map((e) => Number(txt(e)))));
  return a ? mark(a, 'click') : 'none';
}
"""

_DOM_QUIET_JS = """
() => new Promise((resolve) => {
  let timer = setTimeout(done, 700);
  const cap = setTimeout(done, 5000);
  const observer = new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(done, 700); });
  observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
  function done() { observer.disconnect(); clearTimeout(timer); clearTimeout(cap); resolve(true); }
})
"""

_INVENTORY_JS = r"""
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const text = (el) => (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || el.value || '')
    .replace(/\s+/g, ' ').trim().slice(0, 80);
  const labelFor = (el) => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return text(l); }
    const wrap = el.closest('label'); if (wrap) return text(wrap);
    return el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || '';
  };
  const links = [];
  for (const a of document.querySelectorAll('a[href]')) {
    if (!visible(a)) continue;
    links.push({ text: text(a), href: a.href });
    if (links.length >= 150) break;
  }
  const navSel = 'nav a, nav button, aside a, aside button, header a, header button, [role=menuitem], [role=tab], [role=link], [role=treeitem], .nav-item, .menu-item, li > a';
  const seen = new Set(); const nav_items = [];
  for (const el of document.querySelectorAll(navSel)) {
    const t = text(el); if (!t || seen.has(t) || !visible(el)) continue;
    seen.add(t);
    const href = el.tagName === 'A' ? el.href : null;
    nav_items.push({ text: t, role: el.getAttribute('role') || (el.tagName === 'A' ? 'link' : el.tagName === 'BUTTON' ? 'button' : 'generic'), href });
    if (nav_items.length >= 80) break;
  }
  const buttons = [];
  for (const b of document.querySelectorAll('button, [role=button], input[type=submit], input[type=button]')) {
    const t = text(b); if (!t || !visible(b)) continue;
    buttons.push(t); if (buttons.length >= 60) break;
  }
  const fields = [];
  for (const f of document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea')) {
    // Upload fields are usually hidden behind a styled button — read them
    // anyway: their `accept` is the app's own list of allowed file types.
    if (!visible(f) && f.type !== 'file') continue;
    const item = { label: labelFor(f).slice(0, 80), type: f.tagName === 'SELECT' ? 'select' : (f.type || f.tagName.toLowerCase()), required: f.required || f.getAttribute('aria-required') === 'true' };
    if (f.tagName === 'SELECT') item.options = [...f.options].slice(0, 10).map(o => o.text.trim());
    for (const a of ['min', 'max', 'minlength', 'maxlength', 'pattern', 'accept']) if (f.getAttribute(a)) item[a] = f.getAttribute(a);
    if (f.type === 'file') item.multiple = f.hasAttribute('multiple');
    fields.push(item); if (fields.length >= 60) break;
  }
  const tables = [];
  for (const t of document.querySelectorAll('table, [role=grid]')) {
    if (!visible(t)) continue;
    const headers = [...t.querySelectorAll('th, [role=columnheader]')].map(text).filter(Boolean).slice(0, 15);
    const rows = t.querySelectorAll('tbody tr, [role=row]').length;
    tables.push({ headers, rows }); if (tables.length >= 5) break;
  }
  const alerts = [...document.querySelectorAll('[role=alert], [role=status], .alert, .toast, .error, .invalid-feedback')]
    .filter(visible).map(text).filter(Boolean).slice(0, 10);
  const headings = [...document.querySelectorAll('h1, h2, h3')].filter(visible).map(text).filter(Boolean).slice(0, 12);
  return { title: document.title, url: location.href, headings, links, nav_items, buttons, fields, tables, alerts,
           body_text: (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').slice(0, 2500) };
}
"""


@dataclass
class HealthSignal:
    kind: str  # crash | broken_link | server_error | background_error | slow
    severity: str
    title: str
    detail: str
    url: str


@dataclass
class Visit:
    url: str
    status: int | None
    load_ms: int
    inventory: dict[str, Any]
    shot: bytes
    signals: list[HealthSignal] = field(default_factory=list)


# A locator Explorer actually used, as data: recorded on each step and used
# as-is by the replay and the exported test (testkit.ts_locator), so a test
# never re-guesses how to find an element it already found once.
#   {"by": "role", "role": "checkbox", "name": "Rear", "exact": True}
#   {"by": "label" | "text", "text": ..., "exact": bool}
#   {"by": "placeholder", "text": ...}   {"by": "css", "selector": ...}
#   {"by": "select_label", "text": field} {"by": "select_with", "option": option}
def locate(page: Any, spec: dict[str, Any]) -> Any:
    by = spec.get("by")
    if by == "role":
        return page.get_by_role(spec["role"], name=spec["name"], exact=bool(spec.get("exact")))
    if by in ("label", "select_label"):
        return page.get_by_label(spec["text"], exact=bool(spec.get("exact")))
    if by == "placeholder":
        return page.get_by_placeholder(spec["text"])
    if by == "text":
        return page.get_by_text(spec["text"], exact=bool(spec.get("exact")))
    if by == "css":
        return page.locator(spec["selector"])
    if by == "select_with":
        return page.locator("select").filter(has=page.locator("option", has_text=spec["option"]))
    raise ValueError(f"unknown locator {spec!r}")


def _role(role: str, name: str, exact: bool = True) -> dict[str, Any]:
    return {"by": "role", "role": role, "name": name, "exact": exact}


def field_after_caption(caption: str) -> str:
    """The first field after text reading exactly `caption`: forms that put
    a caption above a field without linking them (no `<label for>`). The
    exported test uses the same locator (testkit)."""
    return (
        f'xpath=//*[normalize-space(text())="{caption}"]'
        "/following::*[self::input or self::select or self::textarea][1]"
    )


class Eyes:
    def __init__(self, base_url: str, page: Page | None = None) -> None:
        parts = urlsplit(base_url)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        # An existing page can be borrowed (e.g. a second tab with a
        # different clock); it then has no listeners or recording of its own.
        self.page: Page | None = page
        # Where a test's route may begin: the app's start address and where
        # sign-in landed (see sense.route_starts_at_entry).
        self.entry_urls: set[str] = {base_url}
        self._pending: list[HealthSignal] = []
        # The page's data calls (method, address, status), for API proofs.
        self.calls: list[tuple[str, str, int]] = []
        self._calls_from = 0
        self._starts_fresh = False
        self._login: tuple[str, str, str] | None = None
        self._typed_name = ""  # last non-password value typed (lockout guard)
        self.last_suggestion: str | None = None  # picked by the last fill_field
        # The locator the last fill/choose/click actually used (see `locate`).
        self.last_locator: dict[str, Any] | None = None

    async def open(
        self, storage_state: dict[str, Any] | None = None, record_dir: str | None = None
    ) -> None:
        """`record_dir` turns on screen recording (one .webm for the whole
        session, available from `close()`)."""
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            viewport=VIEWPORT,
            storage_state=storage_state,  # pyright: ignore[reportArgumentType]
            ignore_https_errors=True,
            record_video_dir=record_dir,
            record_video_size=VIEWPORT if record_dir else None,
        )
        await self._context.route("**/*", _serve_static)
        self.page = await self._context.new_page()
        self.page.on("console", self._on_console)
        self.page.on("pageerror", self._on_page_error)
        self.page.on("response", self._on_response)

    async def close(self) -> str | None:
        """Returns the recording's file path when recording was on."""
        video = self.page.video if self.page is not None else None
        for closer in (self._context, self._browser):
            try:
                if closer is not None:
                    await closer.close()
            except PlaywrightError:
                pass
        path = None
        if video is not None:
            try:
                path = str(await video.path())
            except PlaywrightError:
                path = None
        if self._pw is not None:
            await self._pw.stop()
        return path

    # -- health listeners ---------------------------------------------------
    def _here(self) -> str:
        return self.page.url if self.page else ""

    def _on_console(self, message: Any) -> None:
        if message.type == "error":
            self._pending.append(
                HealthSignal(
                    "background_error",
                    "low",
                    "Error in the page's background code",
                    message.text[:400],
                    self._here(),
                )
            )

    def _on_page_error(self, error: Any) -> None:
        self._pending.append(
            HealthSignal(
                "background_error",
                "medium",
                "The page's code crashed while running",
                str(error)[:400],
                self._here(),
            )
        )

    def _on_response(self, response: Any) -> None:
        status = response.status
        if response.request.resource_type in ("xhr", "fetch"):
            self.calls.append((response.request.method, response.url, status))
            # ponytail: kept in memory per browser; trim the oldest past 500.
            if len(self.calls) > 500:
                del self.calls[:100]
                self._calls_from = max(0, self._calls_from - 100)
        if status >= 500:
            self._pending.append(
                HealthSignal(
                    "server_error",
                    "high",
                    f"Server error {status}",
                    f"{response.request.method} {response.url[:300]}",
                    self._here(),
                )
            )

    # -- actions ------------------------------------------------------------
    def mark_calls(self) -> None:
        """From here on, `calls_since_mark` only has the calls a test makes."""
        self._calls_from = len(self.calls)

    def calls_since_mark(self) -> list[tuple[str, str, int]]:
        return self.calls[self._calls_from :]

    async def settle(self, budget_ms: int = 7000) -> None:
        assert self.page is not None
        try:
            await self.page.wait_for_load_state("networkidle", timeout=budget_ms)
        except PlaywrightTimeout:
            pass
        # Single-page apps keep drawing after the network goes quiet: wait
        # until the page stops changing for a moment (capped).
        try:
            await self.page.evaluate(_DOM_QUIET_JS)
        except PlaywrightError:
            await self.page.wait_for_timeout(600)

    async def wait_for_change(self, before: str, timeout_ms: int = 10000) -> bool:
        """After pressing something: wait until the screen actually changes
        (slow lookups can take seconds), then let it settle."""
        assert self.page is not None
        for _ in range(timeout_ms // 500):
            if await self.fingerprint() != before:
                await self.settle()
                return True
            await self.page.wait_for_timeout(500)
        return False

    async def goto(self, url: str) -> tuple[int | None, int]:
        assert self.page is not None
        started = time.monotonic()
        status: int | None = None
        try:
            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = response.status if response else None
        except PlaywrightTimeout:
            self._pending.append(
                HealthSignal(
                    "crash",
                    "high",
                    "Screen never finished loading",
                    "Gave up after 30 seconds",
                    url,
                )
            )
        except PlaywrightError as exc:
            self._pending.append(
                HealthSignal("crash", "high", "Screen could not be opened", str(exc)[:300], url)
            )
        await self.settle()
        return status, int((time.monotonic() - started) * 1000)

    async def browser(self, action: str) -> bool:
        """The browser's own Back ("back") or Refresh ("reload") button."""
        assert self.page is not None
        try:
            if action == "back":
                await self.page.go_back(wait_until="domcontentloaded", timeout=30000)
            else:
                await self.page.reload(wait_until="domcontentloaded", timeout=30000)
        except PlaywrightError:
            return False
        await self.settle()
        return True

    async def click_text(
        self, label: str, role: str | None = None, spec: dict[str, Any] | None = None
    ) -> bool:
        """Click something by what a person reads on it — or, replaying,
        exactly by the locator that worked before (`spec`). Returns False
        when nothing matching is on screen."""
        assert self.page is not None
        self.last_locator = None
        specs: list[dict[str, Any]] = []
        if spec:
            specs = [spec]
        else:
            if role in ("link", "button", "menuitem", "tab", "treeitem"):
                specs.append(_role(role, label))
            specs += [
                _role("link", label),
                {"by": "text", "text": label, "exact": True},
                # Icons and arrows around the words ("🔒 Generate Card PIN ›").
                _role("link", label, exact=False),
                _role("button", label, exact=False),
            ]
        for candidate in specs:
            try:
                target = locate(self.page, candidate).filter(visible=True).first
                if await target.count():
                    await target.click(timeout=5000)
                    await self.settle()
                    self.last_locator = candidate
                    return True
            except PlaywrightError:
                continue
        return False

    async def look(self, url_hint: str, status: int | None, load_ms: int) -> Visit:
        """Read the current screen + collect health signals since last look."""
        assert self.page is not None
        try:
            inventory: dict[str, Any] = await self.page.evaluate(_INVENTORY_JS)
        except PlaywrightError:
            inventory = {
                "title": "",
                "url": self.page.url,
                "headings": [],
                "links": [],
                "nav_items": [],
                "buttons": [],
                "fields": [],
                "tables": [],
                "alerts": [],
                "body_text": "",
            }
        shot = await self.page.screenshot(type="jpeg", quality=70)
        signals, self._pending = self._pending, []
        if status is not None and status >= 400:
            kind, severity = (
                ("server_error", "high") if status >= 500 else ("broken_link", "medium")
            )
            signals.append(
                HealthSignal(kind, severity, f"Screen returned {status}", url_hint, url_hint)
            )
        if load_ms > SLOW_LOAD_MS:
            signals.append(
                HealthSignal(
                    "slow",
                    "low",
                    "Slow screen",
                    f"Took {load_ms / 1000:.1f}s to settle",
                    self.page.url,
                )
            )
        return Visit(self.page.url, status, load_ms, inventory, shot, signals)

    async def sign_in(self, login_url: str, username: str, password: str) -> bool:
        """Sign in, retrying when the server fails the attempt (5xx) — apps
        often do when several browsers sign in as one user at once. The
        login is kept so a mission that gets signed out can sign back in."""
        self._login = (login_url, username, password)
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(2 * attempt)
            signed_in = await self._sign_in_once(login_url, username, password)
            if signed_in is not None:
                return signed_in
        return False

    def remember_login(self, login_url: str, username: str, password: str) -> None:
        """Know the saved login without signing in (sign-in tests type it)."""
        self._login = (login_url, username, password)

    def _login_value(self, value: str) -> str:
        """`{{username}}` / `{{password}}` -> the saved login. The recorded
        step and the exported test keep the placeholder, never the secret."""
        token = value.strip().lower()
        if self._login and token in ("{{username}}", "{{password}}"):
            return self._login[1] if token == "{{username}}" else self._login[2]
        return value

    async def forget_session(self) -> None:
        """Back to signed out: no cookies, nothing stored by the app."""
        assert self.page is not None
        await self.page.context.clear_cookies()
        try:
            await self.page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        except PlaywrightError:
            pass  # about:blank or a page that forbids storage

    async def sign_in_again(self) -> bool:
        return self._login is not None and await self.sign_in(*self._login)

    async def on_sign_in_screen(self) -> bool:
        """Exactly one visible password box is a sign-in form; change-password
        and sign-up forms have two or more."""
        assert self.page is not None
        try:
            return await self.page.locator("input[type=password]:visible").count() == 1
        except PlaywrightError:
            return False

    async def _sign_in_once(self, login_url: str, username: str, password: str) -> bool | None:
        """Find the password box, the identity box before it, fill both,
        submit. True when the password box is gone afterwards (we got past
        the login screen); None when the server failed the attempt."""
        assert self.page is not None
        await self.goto(login_url)
        password_box = self.page.locator("input[type=password]:visible").first
        if not await self._appears(password_box):
            # Maybe a "Sign in" link/button leads to the form.
            for label in ("Sign in", "Log in", "Login", "Sign In", "Log In"):
                if await self.click_text(label):
                    break
            if not await self._appears(password_box):
                return True  # nothing to sign in to — app is open
        # The identity box is the last visible text-like input before the
        # password box (many apps leave `type` off entirely).
        marked = await self.page.evaluate(
            """() => {
              const pw = [...document.querySelectorAll('input[type=password]')].find(e => e.offsetParent);
              const textLike = [...document.querySelectorAll('input')].filter(e =>
                e.offsetParent && ['', 'text', 'email', 'tel'].includes((e.getAttribute('type') || '').toLowerCase()));
              const before = textLike.filter(e => pw && (e.compareDocumentPosition(pw) & Node.DOCUMENT_POSITION_FOLLOWING));
              const pick = before[before.length - 1] || textLike[0];
              if (!pick) return false;
              pick.setAttribute('data-explorer-identity', '1');
              return true;
            }"""
        )
        if not marked:
            return False
        await self.page.locator("[data-explorer-identity]").first.fill(username)
        await password_box.fill(password)
        failed: list[int] = []

        def on_response(response: Any) -> None:
            if response.request.is_navigation_request() and response.status >= 500:
                failed.append(response.status)

        self.page.on("response", on_response)
        try:
            submitted = await self._press_sign_in()
            if not submitted:
                await password_box.press("Enter")
            await self.settle(10000)
        finally:
            self.page.remove_listener("response", on_response)
        if failed:
            return None
        try:
            # Some sign-ins answer slowly: give the login screen time to go.
            await self.page.locator("input[type=password]").first.wait_for(
                state="hidden", timeout=15000
            )
        except PlaywrightError:
            pass
        try:
            return not await self.page.locator("input[type=password]").first.is_visible()
        except PlaywrightError:
            return True

    async def _press_sign_in(self) -> bool:
        assert self.page is not None
        for label in ("Sign in", "Log in", "Login", "Sign In", "Log In", "Continue", "Submit"):
            button = self.page.get_by_role("button", name=label, exact=False).first
            if await button.count() and await button.is_visible():
                await button.click()
                return True
        return False

    async def fingerprint(self) -> str:
        """Cheap "did anything change?" check: address + start of the text."""
        assert self.page is not None
        try:
            text = await self.page.evaluate("() => (document.body?.innerText || '').slice(0, 4000)")
        except PlaywrightError:
            text = ""
        # A dead `href="#"` link only appends "#" — that isn't a change.
        return f"{self.page.url.rstrip('#')}::{hash(text)}"

    async def start_fresh_on_resume_prompts(self) -> None:
        """Whether an app asks "resume your saved progress?" depends on what
        earlier runs left behind, so a replay can't rely on seeing it or
        not: whenever it shows, answer 'start over' (Playwright checks before
        every action). Only a screen offering both answers counts — a lone
        'Start over' link on some other screen is left alone."""
        assert self.page is not None
        if self._starts_fresh:
            return
        self._starts_fresh = True
        page = self.page
        fresh = page.get_by_role("button", name=START_FRESH).or_(
            page.get_by_role("link", name=START_FRESH)
        )

        async def answer(button: Any) -> None:
            try:
                if await page.get_by_role("button", name=RESUME_LABEL).count():
                    await button.click(timeout=3000)
                    # Starting over re-renders the screen; let it settle first.
                    await button.wait_for(state="hidden", timeout=10000)
                    await page.evaluate(_DOM_QUIET_JS)
            except PlaywrightError:
                pass  # the prompt went away on its own; nothing to answer

        self._fresh_locator = fresh.first
        await page.add_locator_handler(self._fresh_locator, answer, no_wait_after=True)

    def remember_entry(self) -> None:
        """The page the browser is on now is an entry point (sign-in landed here)."""
        if self.page is not None:
            self.entry_urls.add(self.page.url)

    @property
    def starts_fresh(self) -> bool:
        return self._starts_fresh

    async def start_fresh_if_asked(self) -> bool:
        """Answer a showing "resume your saved progress?" prompt with 'start
        over' now. The locator handler above only fires before Playwright's
        click/fill actions; choosing an option first just looks for it, so on
        a resume prompt left by the previous attempt (FNOL: "Welcome back,
        James") it failed without the handler ever running. The exported
        test does the same check before every step (`startFreshIfAsked`)."""
        assert self.page is not None
        page = self.page
        fresh = (
            page.get_by_role("button", name=START_FRESH)
            .or_(page.get_by_role("link", name=START_FRESH))
            .filter(visible=True)
            .first
        )
        try:
            if not await fresh.count() or not await page.get_by_role(
                "button", name=RESUME_LABEL
            ).count():
                return False
            await fresh.click(timeout=3000)
            await fresh.wait_for(state="hidden", timeout=10000)
            await page.evaluate(_DOM_QUIET_JS)
            return True
        except PlaywrightError:
            return False  # the handler pressed it already, or the prompt went away

    async def stop_starting_fresh(self) -> None:
        """Hand resume prompts back to whoever drives the browser next (a
        mission about resuming a saved report must see the prompt)."""
        if self.page is not None and self._starts_fresh and getattr(self, "_fresh_locator", None):
            try:
                await self.page.remove_locator_handler(self._fresh_locator)
            except PlaywrightError:
                pass
        self._starts_fresh = False

    async def fill_field(self, label: str, value: str, spec: dict[str, Any] | None = None) -> bool:
        """Type into a field found by what a person reads next to it — or,
        replaying, exactly by the locator that worked before (`spec`)."""
        assert self.page is not None
        value = resolve_relative(self._login_value(value))
        self.last_locator = None
        specs = [spec] if spec else [
            _role("textbox", label),
            _role("spinbutton", label),
            _role("combobox", label),
            _role("textbox", label, exact=False),
            {"by": "placeholder", "text": label},
            {"by": "label", "text": label, "exact": True},
            *([{"by": "css", "selector": field_after_caption(label)}] if '"' not in label else []),
        ]
        for candidate in specs:
            try:
                target = locate(self.page, candidate).filter(visible=True).first
                if not await target.count():
                    continue
                self.last_locator = candidate
                if not value.strip():
                    # Clearing only counts if the box really ends up empty —
                    # a picker that keeps its default ("Just now") must not
                    # read as "left blank", or the test reports a false bug.
                    if await target.evaluate("e => e.readOnly === true"):
                        await target.click(timeout=3000)
                        await self.page.keyboard.press("ControlOrMeta+A")
                        await self.page.keyboard.press("Delete")
                        await self.page.keyboard.press("Escape")
                    else:
                        await target.fill("", timeout=5000)
                    return not (await target.input_value()).strip()
                if await target.evaluate("e => e.readOnly === true"):
                    return await self._type_into_picker(target, value)
                if await target.get_attribute("type") == "password":
                    if self._login and self._typed_name == self._login[1] != "":
                        if value != self._login[2]:
                            # A wrong password for the real account locks it
                            # after a few tries: wrong-login tests must use a
                            # made-up name instead.
                            return False
                else:
                    self._typed_name = value
                await target.fill(value, timeout=5000)
                self.last_suggestion = await self._pick_suggestion(target, value)
                return True
            except PlaywrightError:
                continue
        return False

    async def _pick_suggestion(self, box: Any, typed: str) -> str | None:
        """A type-ahead field ("Employee Name", a city) only takes a value
        picked from its suggestions: pick the one that contains what was
        typed. None when the field offers no suggestions."""
        assert self.page is not None
        looks_typeahead = await box.evaluate(
            """e => !!(e.getAttribute('aria-autocomplete') || e.getAttribute('list')
              || e.getAttribute('role') === 'combobox'
              || /type|search|hint|start typing/i.test(e.getAttribute('placeholder') || ''))"""
        )
        options = (
            self.page.get_by_role("option")
            .filter(visible=True)
            .filter(has_text=re.compile(re.escape(typed.strip()[:40]), re.IGNORECASE))
        )
        # Suggestions often say "Searching..." first: wait a little for them.
        for _ in range(10 if looks_typeahead else 1):
            await self.page.wait_for_timeout(300)
            if await options.count():
                text = (await options.first.inner_text()).strip()
                await options.first.click(timeout=3000)
                return text[:200] or None
        return None

    async def present(self, step: dict[str, Any]) -> bool:
        """Is what this recorded step acts on on screen right now? (Used by
        replays to tell "the app skipped this screen this time" apart from
        "this step is broken".)"""
        assert self.page is not None
        page, do = self.page, step.get("do")
        if do == "click":
            label = str(step.get("label") or "")
            locators = [
                page.get_by_role("button", name=label, exact=True),
                page.get_by_role("link", name=label, exact=True),
                page.get_by_text(label, exact=True),
            ]
        elif do == "fill":
            field = str(step.get("field") or "")
            locators = [
                page.get_by_role("textbox", name=field, exact=True),
                page.get_by_placeholder(field),
                page.get_by_label(field, exact=True),
                page.get_by_role("textbox", name=field),
            ]
        elif do == "choose":
            option = str(step.get("option") or "")
            locators = [
                page.get_by_role("radio", name=option, exact=True),
                page.get_by_label(option, exact=True),
                page.get_by_role("checkbox", name=option, exact=True),
                page.get_by_role("button", name=option, exact=True),
                page.get_by_text(option, exact=True),
            ]
        elif do == "upload":
            locators = [page.locator("input[type=file]")]
        else:
            return False
        for locator in locators:
            try:
                if await locator.filter(visible=True).count():
                    return True
            except PlaywrightError:
                continue
        return False

    async def press_continue_like(self) -> str | None:
        """Get past a screen the recorded path didn't have (a "you already
        reported something similar" or "welcome back" stop): press its
        continue-style button. Returns the label pressed, or None."""
        assert self.page is not None
        for role in ("button", "link"):
            buttons = self.page.get_by_role(role).filter(visible=True)
            try:
                count = min(await buttons.count(), 40)
                for i in range(count):
                    label = " ".join((await buttons.nth(i).inner_text(timeout=1000)).split())
                    if (
                        label
                        and CONTINUE_LIKE.search(label)
                        and not RESUME_LABEL.search(label)
                        and not looks_final(label)
                    ):
                        before = await self.fingerprint()
                        await buttons.nth(i).click(timeout=5000)
                        if await self.wait_for_change(before, 8000):
                            return label
            except PlaywrightError:
                continue
        return None

    async def _choose_by(self, candidate: dict[str, Any], option: str) -> bool:
        """Select `option` through one locator. Choosing means "make sure
        it's selected": a box a saved draft already ticked is left ticked."""
        assert self.page is not None
        try:
            target = locate(self.page, candidate).filter(visible=True).first
            if not await target.count():
                return False
            if candidate.get("by") in ("select_label", "select_with"):
                await target.select_option(label=option, timeout=5000)
            else:
                checkable = await target.evaluate(
                    "e => e.matches('input[type=checkbox],input[type=radio],[role=checkbox],"
                    "[role=radio]')"
                )
                if not (checkable and await target.is_checked(timeout=2000)):
                    await target.click(timeout=5000)
            self.last_locator = candidate
            return True
        except PlaywrightError:
            return False

    async def upload_file(self, label: str, path: str) -> bool:
        """Attach a file the way the page expects it. Upload areas usually
        hide the real <input type=file> behind a drop zone, so set it
        directly; with several, prefer the one labelled `label`. Without any
        such input, press the labelled control and answer the file picker."""
        assert self.page is not None
        inputs = self.page.locator("input[type=file]")
        try:
            count = await inputs.count()
            if count:
                target = inputs.first
                if count > 1 and label:
                    labelled = self.page.get_by_label(label).and_(inputs)
                    if await labelled.count():
                        target = labelled.first
                await target.set_input_files(path, timeout=5000)
                await self.settle()
                return True
            if label:
                async with self.page.expect_file_chooser(timeout=5000) as chooser:
                    await self.page.get_by_text(label).first.click(timeout=3000)
                await (await chooser.value).set_files(path)
                await self.settle()
                return True
        except PlaywrightError:
            pass
        return False

    async def _type_into_picker(self, target: Any, value: str) -> bool:
        """Read-only boxes are usually date/time pickers. Typing into them
        only changes the box's text, not the app's own value (the app then
        rejects the step), so first use the picker like a person: open it,
        move to the month, click the day. Only if no calendar opens, type
        the value in common display formats until one sticks."""
        assert self.page is not None
        if await self._pick_from_calendar(target, value):
            return True
        for candidate in date_variants(value):
            await target.evaluate("e => e.removeAttribute('readonly')")
            await target.click(timeout=3000)
            await self.page.keyboard.press("ControlOrMeta+A")
            await self.page.keyboard.type(candidate)
            await self.page.keyboard.press("Tab")
            await self.page.wait_for_timeout(300)
            # Showing the text isn't enough: the app must accept it.
            if (await target.input_value()).strip() and await target.get_attribute(
                "aria-invalid"
            ) != "true":
                return True
        return False

    async def _pick_from_calendar(self, target: Any, value: str) -> bool:
        """Open the field's calendar and click the date, whatever the
        framework: it relies only on what is on screen (a popup showing a
        month name and year, arrow buttons, day cells)."""
        assert self.page is not None
        match = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})", value)
        if not match:
            return False
        wanted = {"year": int(match[1]), "month": int(match[2]), "day": int(match[3])}
        try:
            await target.click(timeout=3000)
            await self.page.wait_for_timeout(500)
            reopened = False
            for _ in range(40):  # arrows for nearby months, the year grid for far ones
                outcome = await self.page.evaluate(_CALENDAR_JS, wanted)
                if outcome == "none" and not reopened:
                    # The calendar was already open and the click toggled it shut.
                    reopened = True
                    await target.click(timeout=3000)
                    await self.page.wait_for_timeout(500)
                    outcome = await self.page.evaluate(_CALENDAR_JS, wanted)
                if outcome == "none":
                    return False
                if outcome == "click":  # an arrow, the header, a year or a month
                    await self.page.locator("[data-explorer-pick]").first.click(timeout=3000)
                    await self.page.wait_for_timeout(300)
                    continue
                await self.page.wait_for_timeout(300)
                if outcome == "pick":
                    await self.page.locator("[data-explorer-pick]").first.click(timeout=3000)
                    await self.page.wait_for_timeout(500)
                    if not (await target.input_value()).strip():
                        # Date-and-time pickers often confirm with a button.
                        for word in ("OK", "Done", "Apply", "Set", "Select"):
                            ok = self.page.get_by_role("button", name=word, exact=True).filter(
                                visible=True
                            )
                            if await ok.count():
                                await ok.first.click(timeout=3000)
                                await self.page.wait_for_timeout(400)
                                break
                    await self.page.keyboard.press("Tab")  # close without cancelling
                    await self.page.wait_for_timeout(300)
                    return bool((await target.input_value()).strip())
        except PlaywrightError:
            return False
        return False

    async def choose(
        self, field_label: str, option: str, spec: dict[str, Any] | None = None
    ) -> bool:
        """Pick an option: a radio/checkbox/button-like option by its text,
        or an option inside a dropdown labelled `field_label` — or,
        replaying, exactly by the locator that worked before (`spec`)."""
        assert self.page is not None
        self.last_locator = None
        if spec:
            return await self._choose_by(spec, option)
        selects: list[dict[str, Any]] = []
        if field_label:
            selects.append({"by": "select_label", "text": field_label})
        # A dropdown with no linked label: the one that offers this option.
        selects.append({"by": "select_with", "option": option})
        for candidate in selects:
            try:
                select = locate(self.page, candidate).filter(visible=True).first
                if await select.count() and await select.evaluate("e => e.tagName") == "SELECT":
                    await select.select_option(label=option, timeout=5000)
                    self.last_locator = candidate
                    return True
            except PlaywrightError:
                pass
        # Already selected (a saved draft)? Leave it: clicking its text would
        # untick it. Recorded as that very box, so a replay checks the same.
        for role in ("checkbox", "radio"):
            already = _role(role, option, exact=False)
            try:
                box = locate(self.page, already).filter(visible=True).first
                if await box.count() and await box.is_checked(timeout=2000):
                    self.last_locator = already
                    return True
            except PlaywrightError:
                pass
        for candidate in (
            _role("radio", option),
            {"by": "label", "text": option, "exact": True},
            _role("checkbox", option),
            _role("option", option),
            _role("button", option),
            {"by": "text", "text": option, "exact": True},
            # Last resort: the model's wording is often a shortened label
            # ("Fence" for "Fence or gate").
            _role("checkbox", option, exact=False),
            _role("radio", option, exact=False),
            {"by": "label", "text": option, "exact": False},
        ):
            if await self._choose_by(candidate, option):
                return True
        # Custom dropdowns: open the field, then click the option text. The
        # field is found by its label, or as the first dropdown-like box
        # after its caption (many apps put the caption beside it unlinked).
        if not field_label:
            return False
        openers = [self.page.get_by_label(field_label).first]
        if '"' not in field_label:
            openers.append(
                self.page.locator(
                    f'xpath=//*[normalize-space(text())="{field_label}"]/following::*['
                    "@role='combobox' or @aria-haspopup or contains(@class,'select')][1]"
                ).first
            )
        for opener in openers:
            try:
                if not await opener.count():
                    continue
                await opener.click(timeout=3000)
                await self.page.get_by_role("option", name=option, exact=True).or_(
                    self.page.get_by_text(option, exact=True)
                ).filter(visible=True).first.click(timeout=3000)
                return True
            except PlaywrightError:
                continue
        return False

    async def _appears(self, locator: Any, timeout_ms: int = 10000) -> bool:
        try:
            await locator.wait_for(state="visible", timeout=timeout_ms)
            return True
        except PlaywrightError:
            return False


def storage_state_from(secret: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(secret)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) and "cookies" in parsed else None
