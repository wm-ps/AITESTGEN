"""Autonomous exploration loop — DiscoveryActivity's core crawl behavior
(Story 2.2, stop condition replaced by Story 2.3).

Neither the PRD nor the Architecture Spine specifies an exact traversal
algorithm (FR-6: "navigates the Application the way a thorough tester
would"). This is a sound, non-binding default: breadth-first link traversal,
generic placeholder values keyed by input type for form-filling, and
Playwright response interception for API calls — not a spec to match
exactly.

Stop condition (Story 2.3, AD-10, FR-7): the crawl runs until no new page is
found to visit — exhaustive traversal is the *only* stop condition. There is
deliberately no iteration/safety cap here (PRD §12 Risk item 7, accepted
risk: an Application with unbounded pagination could run indefinitely).

Rework 2026-07-18 (Sprint Change Proposal): emits typed capture records
(`CapturedPage`/`CapturedForm`/`CapturedAction`/`CapturedApiCall`/
`CapturedTransition`) instead of a generic `CapturedEvidence` shape — there is
no `Evidence` table. Also adds three crawl-optimization rules (AC 4-6):
- **Page-fingerprint dedup (AC 4):** `visited_pages` already keys the BFS by
  normalized URL — a page reached via more than one link is only ever
  crawled/interacted-with the first time it's dequeued.
- **Navigation-first (AC 5):** each page's interactions (forms/buttons) are
  exercised exactly once, at first visit — dedup above means a page already
  visited never has its interactions repeated, so newly-discovered
  navigation targets are always what's left to do next; there is no separate
  priority queue to build on top of that.
- **Representative-action sampling (AC 6):** standalone buttons are grouped
  by their visible label; only the first instance of each distinct label is
  clicked and captured (`representative=True`) — the other DOM instances of
  a repeated pattern (e.g. one "Edit" button per grid row) are never clicked
  or written as a separate `Action` row. Widened to up to `_MAX_ACTIONS_PER_PAGE`
  distinct labels per page (page-body content tried before nav/header/footer
  chrome) so a shared site-wide button doesn't crowd out every page-specific
  call-to-action the way a single first-DOM-match previously did.

Bug fix (2026-07-20): `heartbeat()` was only ever called once per page, at
the top of the outer loop, before that page's forms/buttons were processed.
On a real site, one page's form-fill-and-submit or button-click sequence can
itself take close to (or over) the Activity's `heartbeat_timeout` — observed
live: a slow page caused no heartbeat for >120s, Temporal declared the
activity heartbeat-timed-out, and retried `DiscoveryActivity` from scratch —
repeatedly, since retry attempts aren't capped, re-crawling and re-persisting
the entire site every time (a real, user-visible "infinite loop", not the
accepted-risk unbounded-*traversal* case Story 2.3 already documents).
Fixed by heartbeating before each individual form submission and button
click too, not just once per page.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urldefrag, urlencode, urlparse, urlsplit, urlunsplit

from domain import aggregation_key
# Story 2.21: capture-time selector/ranked-locator-candidate extraction
# used to live in this module — extracted to `packages/locator_capture`
# (pure functions, no dependency on crawl-run state) so `execution_worker`'s
# self-heal live inspection can reuse the exact same logic without a
# cross-worker-app dependency on this package. Re-imported under their
# original names so every existing call site below (and every existing
# test importing these names from `discovery_worker.crawler`) keeps working
# unchanged — this is a pure code move, not a behavior change.
from locator_capture import capture_locator_candidates as _capture_locator_candidates
from locator_capture import capture_selector as _capture_selector
from locator_capture.capture import _build_locator_candidates, _is_fragile_locator_value
from playwright.async_api import BrowserContext, Frame, Locator, Page, Response
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from discovery_worker import widgets
from discovery_worker.session import attempt_login

if TYPE_CHECKING:
    # Real imports stay function-local everywhere below (see the "circular
    # import" comments at each call site) — these are for static type
    # checking only, never executed, so they can't reintroduce the cycle.
    from discovery_worker import data_resolver, planner

logger = logging.getLogger(__name__)

_GENERIC_VALUES = {
    "email": "test@example.com",
    "tel": "555-0100",
    "number": "1",
    "date": "2026-01-01",
    "text": "Test value",
    "textarea": "Test value",
}

# A field's declared `type` isn't a reliable signal on its own — a quantity
# box is routinely `type="text"` on real sites, and a generic string value
# there (e.g. "Add to Cart" with quantity="Test value") 500s the server
# instead of landing on a real page. Checked by name/id before falling back
# to `_GENERIC_VALUES` below.
_QUANTITY_FIELD_RE = re.compile(r"qty|quantity|count|amount|number", re.IGNORECASE)


def _generic_value(input_type: str, name: str | None, field_id: str | None) -> str:
    if _QUANTITY_FIELD_RE.search(name or field_id or ""):
        return "1"
    return _GENERIC_VALUES.get(input_type, "Test value")


# `on_diagnostic(kind, payload)` — Story 2.22 Task 1's sink contract, called
# from crawler.py (which has no DB session of its own) exactly like
# `on_capture`: the caller (`discovery_activity`) wraps the real
# `record_diagnostic()` off the event loop. `None` is a valid caller (older
# call sites, or a story that hasn't wired it up) — every call site below
# guards with `if on_diagnostic:`.
DiagnosticCallback = Callable[[str, dict], None]


async def _emit_diagnostic(on_diagnostic: DiagnosticCallback, kind: str, payload: dict) -> None:
    """Every `on_diagnostic` call site awaits this rather than calling the
    callback directly — same reason `_CaptureSink.add` hops `on_capture` onto
    a thread: the real callback (`activities.py`'s `_record_diagnostic`)
    does a synchronous Postgres commit, and it shares the same `Session` as
    every capture write, so it must stay serialized with them (awaited, not
    fire-and-forget) rather than run concurrently against that session."""
    await asyncio.to_thread(on_diagnostic, kind, payload)


DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS = 15.0

# Story 2.9 AC 1a: kept small and centralized so it's easy to extend.
_ANALYTICS_HOST_RE = re.compile(
    r"google-analytics\.com|googletagmanager\.com|segment\.(io|com)|"
    r"mixpanel\.com|hotjar\.com|doubleclick\.net|facebook\.net|"
    r"intercom\.io|fullstory\.com|sentry\.io|bugsnag\.com",
    re.IGNORECASE,
)
# A request repeating to the same URL at least this many times, with no
# interval varying by more than the jitter below, is classified a poll /
# long-poll / heartbeat rather than genuine application traffic (AC 1a).
_POLLING_MIN_OCCURRENCES = 3
_POLLING_JITTER_SECONDS = 1.0
_NETWORK_QUIET_WINDOW_SECONDS = 0.5
_NETWORK_POLL_INTERVAL_SECONDS = 0.1
_MAX_INFLIGHT_AGE_SECONDS = 8.0
_DOM_QUIET_WINDOW_MS = 300


@dataclass
class ReadinessResult:
    settled: bool
    unsettled_signals: list[str] = field(default_factory=list)


class NetworkActivityTracker:
    """Network-quiet signal (Story 2.9 AC 1a). Attached once per page — same
    lifetime as Story 2.2's separate `page.on("response", ...)` listener
    used for API-call capture — not a second listener stack per readiness
    check. Tracks in-flight requests and each URL's recent request
    timestamps, so a repeating poll can be recognized and ignored."""

    def __init__(self) -> None:
        self._inflight: dict = {}
        self._history: dict[str, list[float]] = {}

    def attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("requestfinished", self._on_request_settled)
        page.on("requestfailed", self._on_request_settled)

    def _is_ignorable(self, request) -> bool:
        if _ANALYTICS_HOST_RE.search(urlparse(request.url).netloc):
            return True
        times = self._history.get(request.url, [])
        if len(times) >= _POLLING_MIN_OCCURRENCES:
            recent = times[-_POLLING_MIN_OCCURRENCES:]
            # `recent` and `recent[1:]` are deliberately different lengths —
            # this pairs up consecutive timestamps to compute intervals
            # between them, not a same-length zip. `[FIXED]` `strict=True`
            # here always raised, and that exception firing inside a
            # Playwright request event handler (called synchronously by
            # pyee for every single request) was destabilizing the whole
            # page's event dispatch — this is what made readiness
            # mysteriously time out on completely static pages.
            intervals = [b - a for a, b in zip(recent, recent[1:])]
            if intervals and (max(intervals) - min(intervals)) < _POLLING_JITTER_SECONDS:
                return True
        return False

    def _on_request(self, request) -> None:
        self._history.setdefault(request.url, []).append(time.monotonic())
        if not self._is_ignorable(request):
            self._inflight[request] = time.monotonic()

    def _on_request_settled(self, request) -> None:
        self._inflight.pop(request, None)

    def quiet(self) -> bool:
        # A request Playwright never reported finished/failed for (a
        # WebSocket/SSE/long-poll, or a request Chromium silently dropped
        # across a navigation without an event) would otherwise block
        # "quiet" forever — one orphaned entry poisoning every readiness
        # check for the rest of the crawl. Same survivability principle as
        # the polling/analytics heuristics above: an imperfect classifier is
        # fine because the timeout ceiling makes the worst case bounded,
        # never an unbounded hang. Expire anything older than this.
        now = time.monotonic()
        self._inflight = {
            request: started
            for request, started in self._inflight.items()
            if now - started < _MAX_INFLIGHT_AGE_SECONDS
        }
        return len(self._inflight) == 0


async def _wait_for_network_quiet(
    tracker: NetworkActivityTracker | None, deadline: float, heartbeat: Callable[[], None] | None
) -> bool:
    if tracker is None:
        return True
    quiet_since: float | None = None
    while True:
        now = time.monotonic()
        if now >= deadline:
            return False
        if tracker.quiet():
            quiet_since = quiet_since if quiet_since is not None else now
            if now - quiet_since >= _NETWORK_QUIET_WINDOW_SECONDS:
                return True
        else:
            quiet_since = None
        if heartbeat:
            heartbeat()
        await asyncio.sleep(min(_NETWORK_POLL_INTERVAL_SECONDS, max(0.0, deadline - now)))


# Story 2.9 AC 1b/2: an in-page `MutationObserver`, not driver-side polling —
# one `evaluate` round-trip instead of dozens, and it sees every mutation
# batch rather than sampling state between polls (a burst that starts and
# finishes between two polls would otherwise look "stable" mid-render). The
# JS side owns its own ceiling (`maxWaitMs`) so the observer disconnects on
# both the settled and timed-out paths regardless of what the Python side
# does — it can't leak across navigations waiting on a Python-side timeout
# that races ahead of it.
_DOM_STABLE_SCRIPT = """
([quietWindowMs, maxWaitMs]) => new Promise((resolve) => {
  const start = Date.now();
  let lastMutation = start;
  const observer = new MutationObserver(() => { lastMutation = Date.now(); });
  observer.observe(document.documentElement, {
    childList: true, subtree: true, attributes: true, characterData: true,
  });
  const check = () => {
    const now = Date.now();
    if (now - lastMutation >= quietWindowMs) {
      observer.disconnect();
      resolve(true);
    } else if (now - start >= maxWaitMs) {
      observer.disconnect();
      resolve(false);
    } else {
      setTimeout(check, 50);
    }
  };
  check();
})
"""


async def _wait_for_dom_stable(page: Page, remaining_seconds: float) -> bool:
    if remaining_seconds <= 0:
        return False
    remaining_ms = remaining_seconds * 1000
    try:
        return bool(
            await asyncio.wait_for(
                page.evaluate(_DOM_STABLE_SCRIPT, [_DOM_QUIET_WINDOW_MS, remaining_ms]),
                timeout=remaining_seconds + 1.0,
            )
        )
    except Exception:
        return False


_CONTENT_PRESENT_SCRIPT = "document.body && document.body.innerText.trim().length > 0"


async def _wait_for_content_present(page: Page, remaining_seconds: float) -> bool:
    if remaining_seconds <= 0:
        try:
            return bool(await page.evaluate(_CONTENT_PRESENT_SCRIPT))
        except Exception:
            return False
    try:
        await page.wait_for_function(_CONTENT_PRESENT_SCRIPT, timeout=remaining_seconds * 1000)
        return True
    except Exception:
        return False


async def wait_for_page_ready(
    page: Page,
    timeout_seconds: float,
    network_tracker: NetworkActivityTracker | None = None,
    heartbeat: Callable[[], None] | None = None,
    on_diagnostic: DiagnosticCallback | None = None,
) -> ReadinessResult:
    """Story 2.9 AC 1-3: the one settle gate every capture point in this
    file uses. Three signals — network quiet, DOM stable, content present.
    Network-quiet and DOM-stable run concurrently, not sequentially: both
    conditions describe the *same* moment ("is the page settled right now"),
    not two separate phases, and running them concurrently against the same
    deadline roughly halves the guaranteed minimum latency (each has its own
    ~0.3-0.5s settle window) versus paying both windows back-to-back for no
    correctness gain. Content-present runs last (usually near-instant) and
    every signal is bounded by whatever's left of `timeout_seconds`, so the
    total can never exceed the ceiling. On expiry, returns `settled=False`
    rather than raising: readiness has exactly two outcomes, "settled" and
    "settled-enough-by-timeout", and both proceed to capture (AC 3) — never
    blocks, fails, retries or aborts the run."""
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    unsettled: list[str] = []

    network_ok, dom_ok = await asyncio.gather(
        _wait_for_network_quiet(network_tracker, deadline, heartbeat),
        _wait_for_dom_stable(page, deadline - time.monotonic()),
    )
    if not network_ok:
        unsettled.append("network_quiet")
    if not dom_ok:
        unsettled.append("dom_stable")
    if heartbeat:
        heartbeat()

    if not await _wait_for_content_present(page, deadline - time.monotonic()):
        unsettled.append("content_present")

    settled = not unsettled
    if not settled:
        logger.warning(
            "DISC-004: page did not fully settle within %.1fs (unsettled: %s) — "
            "capturing best-effort",
            timeout_seconds,
            unsettled,
        )
        if on_diagnostic:
            # Story 2.18 AC 2/3: informational, not a skip — AC 3's
            # readiness gate still proceeds to best-effort capture (Dev
            # Notes: never blocks/fails/retries/aborts). Logged once per
            # unsettled page visit, not retried here — the timeout itself is
            # already the bounded wait this AC asks for.
            await _emit_diagnostic(
                on_diagnostic,
                "discovery_error",
                {
                    "error_code": "DISC-004",
                    "message": (
                        f"Page did not fully settle within {timeout_seconds:.1f}s "
                        f"(unsettled signals: {', '.join(unsettled)}). Consider increasing "
                        "the Page Load Timeout for this application."
                    ),
                    "page_url": page.url,
                    "retry_count": 0,
                },
            )
    return ReadinessResult(settled=settled, unsettled_signals=unsettled)


# Story 2.9 AC 5/6: bounded sampling of a repeating region (infinite scroll /
# "Load More"), not exhaustion. A hard per-page budget is the backstop; the
# consecutive-SAME rule below is the primary mechanism.
_LOAD_MORE_NAME_RE = re.compile(r"load\s*more|show\s*more|^next$", re.IGNORECASE)
_SCROLL_SAMPLE_BUDGET = 20
_SAME_RUN_TO_CONFIRM_SAMPLED = 3


async def _page_has_scrollable_overflow(page: Page) -> bool:
    try:
        return bool(
            await page.evaluate("document.documentElement.scrollHeight > window.innerHeight + 50")
        )
    except Exception:
        return False


async def _detect_load_more_control(page: Page) -> Locator | None:
    for role in ("button", "link"):
        try:
            locator = page.get_by_role(role, name=_LOAD_MORE_NAME_RE)
            if await locator.count() > 0:
                return locator.first
        except Exception:
            continue
    return None


async def _sample_scroll_or_pagination(
    page: Page,
    page_url: str,
    heartbeat: Callable[[], None] | None,
    on_diagnostic: DiagnosticCallback | None,
    network_tracker: NetworkActivityTracker | None,
    timeout_seconds: float,
) -> str | None:
    """Loops act -> re-observe -> compare, per AC 5/6. Returns the Load-More
    control's accessible name (so the caller excludes it from the generic
    button loop) or `None` if this page uses plain scroll instead."""
    control = await _detect_load_more_control(page)
    control_label: str | None = None
    if control is not None:
        try:
            control_label = (await control.inner_text()).strip() or None
        except Exception:
            control_label = None
    elif not await _page_has_scrollable_overflow(page):
        # Nothing to sample — most pages. Skip the loop entirely rather than
        # pay this function's settle-window cost for a scroll that can't
        # reveal anything.
        return None

    async def _element_count() -> int:
        try:
            return await page.evaluate("document.querySelectorAll('*').length")
        except Exception:
            return -1

    same_streak = 0
    previous_count = await _element_count()
    for iteration in range(_SCROLL_SAMPLE_BUDGET):
        if heartbeat:
            heartbeat()
        try:
            if control is not None:
                await control.click(timeout=1500)
            else:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            break
        await wait_for_page_ready(page, timeout_seconds, network_tracker, heartbeat)
        new_count = await _element_count()
        # `ponytail:` temporary substitute for Story 2.10's SAME/VARIANT/NEW
        # classification (not built yet, per this story's own AC 7) —
        # element-count growth answers "did anything appear?", not "is what
        # appeared the same kind of thing?". It cannot distinguish "10 more
        # identical rows" from "10 more genuinely different rows"; the hard
        # budget above is what bounds that worst case. Upgrade to a real
        # comparison once Story 2.10 lands.
        grew = new_count > previous_count
        same_streak = 0 if grew else same_streak + 1
        previous_count = new_count
        if same_streak >= _SAME_RUN_TO_CONFIRM_SAMPLED:
            if on_diagnostic:
                await _emit_diagnostic(
                    on_diagnostic,
                    "page_readiness",
                    {
                        "type": "scroll_sampled",
                        "page_url": page_url,
                        "reason": "same_run",
                        "iterations": iteration + 1,
                    },
                )
            return control_label
    if on_diagnostic:
        await _emit_diagnostic(
            on_diagnostic,
            "page_readiness",
            {
                "type": "scroll_sampled",
                "page_url": page_url,
                "reason": "budget",
                "iterations": _SCROLL_SAMPLE_BUDGET,
            },
        )
    return control_label


# Story 2.14 AC 1: recurse into same-origin iframes to this depth by default.
DEFAULT_MAX_FRAME_DEPTH = 3

# Story 2.14 AC 6: a minimal, valid placeholder file per upload kind,
# generated once per process and reused across every upload field this run
# encounters (never regenerated per occurrence). A 1x1 transparent PNG and a
# tiny single-page PDF are both small enough to inline as base64 rather than
# ship as separate binary fixture files.
_MINIMAL_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
_MINIMAL_PDF_BYTES = (
    b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 3 3]>>endobj\n"
    b"trailer<</Root 1 0 R>>"
)
_placeholder_files_dir: str | None = None


def _placeholder_file_path(accept: str | None) -> str:
    """Lazily creates one temp dir per process and writes each placeholder
    kind into it exactly once — `accept` (the file input's `accept`
    attribute) picks PDF vs image; anything else defaults to the image, the
    broadest-compatibility choice."""
    global _placeholder_files_dir
    if _placeholder_files_dir is None:
        _placeholder_files_dir = tempfile.mkdtemp(prefix="discovery-upload-")
    wants_pdf = bool(accept) and "pdf" in accept.lower()
    filename = "placeholder.pdf" if wants_pdf else "placeholder.png"
    path = os.path.join(_placeholder_files_dir, filename)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(_MINIMAL_PDF_BYTES if wants_pdf else _MINIMAL_PNG_BYTES)
    return path


# Story 2.14 AC 2 (shadow DOM). `Element.shadowRoot` reads back `null`
# identically for "no shadow root" and "closed shadow root" — there is no
# DOM signal that distinguishes them from outside. The only way to know a
# closed root exists at all is to intercept its creation, so this init
# script (installed once per page, before any app code runs) wraps
# `attachShadow` and tags the host element with a discoverable marker
# attribute recording the mode it was created with.
_SHADOW_TRACKING_INIT_SCRIPT = """
(() => {
  if (window.__discoveryShadowTracking) return;
  window.__discoveryShadowTracking = true;
  window.__discoveryShadowHosts = [];
  const original = Element.prototype.attachShadow;
  let counter = 0;
  Element.prototype.attachShadow = function (init) {
    const root = original.call(this, init);
    const id = 'discovery-shadow-' + (counter++);
    this.setAttribute('data-discovery-shadow-id', id);
    window.__discoveryShadowHosts.push({ id, mode: init && init.mode });
    return root;
  };
})();
"""

# Walks every host tagged by the init script above: open roots (`.shadowRoot`
# non-null) are traversed recursively for interactive elements, feeding AC
# 2's capture requirement; closed roots (`.shadowRoot` reads back null even
# though we know one was attached) are reported separately so the caller can
# log them as unreachable containers rather than silently finding nothing.
_SHADOW_DOM_WALK_SCRIPT = """
() => {
  const hosts = window.__discoveryShadowHosts || [];
  const regions = [];
  const closed = [];
  function describe(el) {
    return {
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role'),
      text: (el.innerText || el.value || '').trim().slice(0, 80),
    };
  }
  function walk(root) {
    const interactive = Array.from(
      root.querySelectorAll('button, a[href], input, select, textarea, [role], [onclick]')
    ).map(describe);
    regions.push(interactive);
    root.querySelectorAll('[data-discovery-shadow-id]').forEach((host) => {
      if (host.shadowRoot) walk(host.shadowRoot);
    });
  }
  hosts.forEach((h) => {
    const host = document.querySelector(`[data-discovery-shadow-id="${h.id}"]`);
    if (!host) return;
    if (host.shadowRoot) {
      walk(host.shadowRoot);
    } else {
      closed.push(describe(host));
    }
  });
  return { regions, closed };
}
"""


async def _collect_shadow_dom_widgets(
    page: Page, page_url: str, on_diagnostic: DiagnosticCallback | None
) -> list[dict]:
    """Runs the walk script and reports closed roots as unreachable
    containers (AC 2). Returns the flattened list of interactive element
    descriptors found inside every open root, for the caller to act on."""
    try:
        data = await page.evaluate(_SHADOW_DOM_WALK_SCRIPT)
    except Exception:
        return []
    for closed_host in data.get("closed", []):
        if on_diagnostic:
            await _emit_diagnostic(
                on_diagnostic,
                "widget_coverage",
                {
                    "type": "unreachable_container",
                    "container": "closed_shadow_root",
                    "page_url": page_url,
                    "host_tag": closed_host.get("tag"),
                },
            )
    interactive: list[dict] = [el for region in data.get("regions", []) for el in region]
    if interactive and on_diagnostic:
        await _emit_diagnostic(
            on_diagnostic,
            "widget_coverage",
            {
                "type": "shadow_dom_traversed",
                "page_url": page_url,
                "element_count": len(interactive),
            },
        )
    return interactive


async def _click_shadow_dom_buttons(
    page: Page,
    sink: _CaptureSink,
    page_url: str,
    shadow_widgets: list[dict],
    seen_labels: set[str],
    heartbeat: Callable[[], None] | None,
) -> None:
    """Playwright's role/text locators already pierce open shadow roots for
    interaction (Dev Notes) — capture just needed to *know the buttons
    exist*, which `_collect_shadow_dom_widgets` provides."""
    for widget in shadow_widgets:
        if widget.get("tag") != "button" or not widget.get("text"):
            continue
        label = widget["text"]
        if label in seen_labels:
            continue
        seen_labels.add(label)
        locator = page.get_by_role("button", name=label, exact=True)
        try:
            if await locator.count() == 0:
                continue
            await locator.first.click(timeout=1500)
        except Exception:
            continue
        if heartbeat:
            heartbeat()
        await sink.add(
            CapturedAction(
                page_url=page_url,
                description=label,
                captured_selector=f'shadow-dom >> role=button[name="{label}"]',
                locator_candidates=await _capture_locator_candidates(
                    locator.first, fallback_text=label
                ),
            )
        )


def _frame_same_origin(frame_url: str, base_url: str) -> bool:
    return frame_url not in ("", "about:blank") and _same_origin(frame_url, base_url)


async def _iter_same_origin_frames(
    frame: Frame,
    depth: int,
    max_depth: int,
    page_url: str,
    on_diagnostic: DiagnosticCallback | None,
):
    """Recurses `frame`'s children to `max_depth` (AC 1), yielding
    `(child_frame, depth)` for each same-origin one. Cross-origin frames are
    logged as unreachable containers — a coverage fact, never an error — and
    not recursed into (their own children are equally unreachable)."""
    for child in frame.child_frames:
        try:
            child_url = child.url
        except Exception:
            continue
        if not _frame_same_origin(child_url, page_url):
            if child_url and child_url != "about:blank" and on_diagnostic:
                await _emit_diagnostic(
                    on_diagnostic,
                    "widget_coverage",
                    {
                        "type": "unreachable_container",
                        "container": "cross_origin_frame",
                        "url": child_url,
                        "page_url": page_url,
                        "depth": depth,
                    },
                )
            continue
        yield child, depth
        if depth < max_depth:
            async for grandchild, d in _iter_same_origin_frames(
                child, depth + 1, max_depth, page_url, on_diagnostic
            ):
                yield grandchild, d
        elif on_diagnostic:
            await _emit_diagnostic(
                on_diagnostic,
                "widget_coverage",
                {"type": "frame_depth_exceeded", "page_url": page_url, "depth": depth},
            )


async def _capture_frame_widgets(
    frame: Frame,
    page_url: str,
    sink: _CaptureSink,
    seen_form_signatures: set,
    heartbeat: Callable[[], None] | None,
    credential: bytes | None,
    on_diagnostic: DiagnosticCallback | None,
    depth: int,
    network_tracker: NetworkActivityTracker | None = None,
    timeout_seconds: float = DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS,
    loop_guard_state: planner.LoopGuardState | None = None,
    data_resolver_pool: dict[str, data_resolver.PoolEntry] | None = None,
    resolution_log: data_resolver.ResolutionLog | None = None,
    safety: planner.SpecialistFn | None = None,
    interaction_level: planner.SpecialistFn | None = None,
) -> None:
    """Runs the same form/button capture routines used for a top-level page,
    scoped to one frame — Dev Notes: extend the existing capture path, don't
    build a parallel one. Everything captured is attributed to `page_url`
    (the containing page), per AC 1. `frame_path` (Story 2.21 AC 3) records
    the container chain so a locator captured inside this frame is still
    resolvable from the top-level page."""
    frame_path = f'iframe[src="{frame.url}"]'
    try:
        form_count = await frame.locator("form").count()
    except Exception:
        form_count = 0
    for form_index in range(form_count):
        try:
            await _fill_and_submit_form(
                frame,
                f"form >> nth={form_index}",
                page_url,
                sink,
                seen_form_signatures,
                heartbeat=heartbeat,
                network_tracker=network_tracker,
                timeout_seconds=timeout_seconds,
                frame_path=frame_path,
                data_resolver_pool=data_resolver_pool,
                resolution_log=resolution_log,
            )
        except Exception:
            logger.warning("frame form capture failed at depth %d on %s", depth, page_url)
    try:
        await _click_standalone_buttons(
            frame,
            sink,
            frame.url,
            heartbeat=heartbeat,
            credential=credential,
            network_tracker=network_tracker,
            timeout_seconds=timeout_seconds,
            frame_path=frame_path,
            loop_guard_state=loop_guard_state,
            safety=safety,
            interaction_level=interaction_level,
        )
    except Exception:
        logger.warning("frame button capture failed at depth %d on %s", depth, page_url)
    if on_diagnostic:
        await _emit_diagnostic(
            on_diagnostic,
            "widget_coverage",
            {
                "type": "frame_traversed",
                "page_url": page_url,
                "frame_url": frame.url,
                "depth": depth,
            },
        )


async def _explore_tabs(
    page: Page,
    sink: _CaptureSink,
    page_url: str,
    heartbeat: Callable[[], None] | None,
    on_diagnostic: DiagnosticCallback | None,
) -> None:
    """Each `role="tab"` is a Tier-1 candidate (AC 3): click it, let its
    revealed content settle, capture it as an Action. Story 2.10/2.11 own
    classifying the revealed content as its own state/VARIANT and formal
    tiering — this story only needs the tab to be discovered and exercised."""
    seen_labels: set[str] = set()
    for tab in await widgets.list_tabs(page):
        try:
            label = (await tab.inner_text()).strip() or await tab.get_attribute("aria-label") or ""
        except Exception:
            continue
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)
        selector = await _capture_selector(tab, fallback_text=label)
        candidates = await _capture_locator_candidates(tab, fallback_text=label)
        try:
            await tab.click(timeout=1500)
        except Exception:
            continue
        if heartbeat:
            heartbeat()
        try:
            await page.wait_for_function(
                "document.body && document.body.innerText.trim().length > 0", timeout=5000
            )
        except Exception:
            pass
        await sink.add(
            CapturedAction(
                page_url=page_url,
                description=f"Tab: {label}",
                captured_selector=selector,
                locator_candidates=candidates,
            )
        )
        if on_diagnostic:
            await _emit_diagnostic(
                on_diagnostic,
                "widget_coverage", {"type": "tab_explored", "page_url": page_url, "label": label}
            )


async def _handle_dialog_if_opened(
    page: Page,
    sink: _CaptureSink,
    page_url: str,
    opener_label: str | None,
    heartbeat: Callable[[], None] | None,
    on_diagnostic: DiagnosticCallback | None,
) -> None:
    """Checked after every click/submit (AC 4): a portal-rendered overlay is
    appended to `document.body`, not a descendant of whatever opened it, so
    this looks for a page-level dialog rather than scoping to the opener's
    subtree. Fingerprints the dialog as a nested state, captures its forms,
    then runs the mandatory close ladder — Dev Notes call an undetected or
    failed close the highest-risk failure in this story."""
    dialog = await widgets.detect_open_dialog(page)
    if dialog is None:
        return
    dialog_url = f"{page_url}#dialog:{opener_label or 'unknown'}"
    if on_diagnostic:
        await _emit_diagnostic(
            on_diagnostic,
            "widget_coverage",
            {"type": "dialog_opened", "page_url": page_url, "opener": opener_label},
        )
    await sink.add(CapturedPage(url=dialog_url, title=f"Dialog: {opener_label or ''}".strip()))
    # Exhaustively driving whatever forms/buttons a dialog contains, at the
    # same fidelity as a full page visit, is Story 2.11's job once tiering
    # exists — this story's job is fingerprinting-as-nested-state (done via
    # the CapturedPage above) and the close ladder below.
    result = await widgets.close_dialog_ladder(page, dialog, page_url, heartbeat=heartbeat)
    if on_diagnostic:
        await _emit_diagnostic(
            on_diagnostic,
            "widget_coverage",
            {
                "type": "dialog_closed",
                "page_url": page_url,
                "method": result.method,
                "closed": result.closed,
            },
        )
        if not result.closed:
            await _emit_diagnostic(
                on_diagnostic,
                "widget_coverage",
                {
                    "type": "unreachable_container",
                    "container": "unclosable_dialog",
                    "page_url": page_url,
                },
            )


async def _handle_popups(
    popup_events: list | None,
    base_url: str,
    sink: _CaptureSink,
    opener_url: str,
    opener_label: str | None,
    on_diagnostic: DiagnosticCallback | None,
) -> None:
    """Drains whatever `page.on("popup", ...)` queued since the last check
    (AC 5). Same-origin + in-scope: followed as a linked sub-flow recorded
    against the opening action. Cross-origin: flagged and closed, never
    followed — focus already stayed on the original page since we never
    switch to the popup beyond reading its URL/title.

    `[FIXED]` A cross-origin popup's own event consistently arrives ~400-500ms
    after the triggering click's promise resolves — measured directly
    against this fixture, not theoretical (Chromium spins up a genuinely
    new renderer process for site-isolated cross-origin content; a
    same-origin popup pays none of that cost and its event is near-
    instant). A short grace wait is not enough margin; 0.75s comfortably
    covers the measured delay. Paid only when nothing is queued yet, so it
    never taxes the (much more common) non-popup click, and is small next
    to the multi-second settle timeouts already paid after every click in
    this file — the alternative is silently missing exactly the case AC 5
    exists to catch."""
    if popup_events is None:
        return
    if not popup_events:
        await asyncio.sleep(0.75)
    while popup_events:
        popup = popup_events.pop(0)
        try:
            await popup.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        try:
            popup_url = popup.url
        except Exception:
            popup_url = ""
        if popup_url and _same_origin(popup_url, base_url):
            try:
                title = await popup.title()
            except Exception:
                title = ""
            await sink.add(CapturedPage(url=popup_url, title=title))
            await sink.add(
                CapturedTransition(
                    from_url=opener_url, to_url=popup_url, triggered_by_description=opener_label
                )
            )
            if on_diagnostic:
                await _emit_diagnostic(
                    on_diagnostic,
                    "widget_coverage",
                    {"type": "popup_followed", "url": popup_url, "opener": opener_label},
                )
        elif on_diagnostic:
            await _emit_diagnostic(
                on_diagnostic,
                "widget_coverage",
                {
                    "type": "unreachable_container",
                    "container": "cross_origin_popup",
                    "url": popup_url,
                    "opener": opener_label,
                },
            )
        try:
            await popup.close()
        except Exception:
            pass

# Representative-action sampling (AC 6): a repeated identical action pattern
# (e.g. one "Edit" per grid row) is exercised once, not once per DOM
# instance — `seen_labels` in `_click_standalone_buttons` is what actually
# enforces this, by distinct label, not a count.
#
# `[FIXED 2026-07-22]` A per-page numeric click budget (`_MAX_ACTIONS_PER_PAGE`,
# later split into independent body/chrome budgets) used to cap how many
# *distinct*-labeled buttons got clicked per page. That directly contradicts
# Story 2.3/AD-10 ("exhaustive traversal is the only stop condition, no
# safety cap") the moment a real page has more distinct nav destinations than
# the budget — observed live: a left-nav sidebar with 13 distinct sections
# only ever got its first 3 tried, silently dropping the rest. Distinct-label
# dedup (below) already prevents the repeated-DOM-instance case this budget
# was originally added for; the count cap was a redundant second limiter that
# only ever did harm. Removed — every distinct label is now tried.
# `[FIXED 2026-07-22]` A dropdown/menu toggle is very often a Bootstrap-style
# `<a>` (e.g. `<a href="#" class="dropdown-toggle">Account</a>`), not a
# `<button>` — the old `//button`-only selector never clicked it, and its
# dead `href` (`#`, `javascript:void(0)`) also fails the same-origin check
# during link scraping, so it was silently invisible to both discovery paths
# at once. This is exactly the "Account" menu hiding Order History/Product
# Management/etc. behind a click the crawler never made. A real `<a href>`
# to an actual destination is left alone here — it's already found via the
# plain link scrape, no need to also click it.
_DEAD_HREF = (
    "not(@href) or normalize-space(@href)='' or normalize-space(@href)='#' "
    "or starts-with(normalize-space(@href), 'javascript:')"
)
# `[FIXED 2026-07-22]` Removing the click budget above means every distinct
# button now genuinely gets tried, including whatever a dropdown reveals —
# observed live: clicking a real app's user-avatar button ("JD") reveals a
# profile dropdown with a real "Log out" action, which the crawler then
# dutifully clicked, ending its own session mid-crawl ("Session expired
# mid-crawl" — a self-inflicted logout, not a real timeout or rate limit).
# An exhaustive crawler that logs itself out can never finish exhaustively —
# no real QA engineer doing exploratory testing would click this either.
# Checked against both the clicked label (here) and the destination URL
# (`_maybe_enqueue` below, for a plain `<a href="/logout">`-shaped link).
_LOGOUT_RE = re.compile(r"log\s*[-_]?\s*out|sign\s*[-_]?\s*out|log\s*[-_]?\s*off", re.IGNORECASE)
# Marks a synthetic label built from an icon's class name (a button with no
# text and no aria-label/title at all) rather than real DOM text — must match
# the literal `'icon:' + cls` built by the JS in `_click_standalone_buttons`.
_ICON_LABEL_PREFIX = "icon:"
_BODY_BUTTONS = (
    f"xpath=//*[(self::button or (self::a and ({_DEAD_HREF}))) "
    "and not(ancestor::form) and not(ancestor::nav) "
    "and not(ancestor::header) and not(ancestor::footer)]"
)
_CHROME_BUTTONS = (
    f"xpath=//*[(self::button or (self::a and ({_DEAD_HREF}))) "
    "and not(ancestor::form) "
    "and (ancestor::nav or ancestor::header or ancestor::footer)]"
)


async def _visible_content_size(page) -> int:
    """`[FIXED 2026-08-05]` Started as a `_BODY_BUTTONS`/`_CHROME_BUTTONS`
    element *count* — wrong signal, confirmed live: this app hides its
    sidebar via a CSS class (`display: none`-equivalent), which never
    removes the `<a>` elements from the DOM, only their visibility. A raw
    `.count()` is a DOM-presence query, blind to CSS visibility, so it
    reported the exact same number whether the drawer was open or closed —
    the grow/shrink check below silently never fired, no matter what the
    click actually did. `document.body.innerText` — like the
    `text_still_present_anywhere` diagnostic already uses — naturally
    excludes hidden elements, so its length is a cheap, single-call, holistic
    stand-in for "how much is currently visible": revealing ~15 sidebar links
    adds a few hundred characters, a real collapse removes them, a no-op
    (clicking something unrelated) leaves it unchanged."""
    try:
        return await page.evaluate("() => document.body.innerText.length")
    except Exception:
        return 0


@dataclass
class CapturedFormField:
    name: str | None
    input_type: str
    required: bool
    default_value: str | None
    captured_selector: str | None
    # Story 2.21: ranked candidate locators, e.g.
    # [{"strategy": "testid", "value": "...", "fragile": False}, ...].
    locator_candidates: list[dict] | None = None
    validation_message: str | None = None


@dataclass
class CapturedPage:
    url: str
    title: str
    object_storage_key: str | None = None
    # Story 2.10: the heading + structural-shape signals `state_identity.py`
    # scores against. `structural_tokens` includes tokens from open shadow
    # roots (Story 2.14) so two states differing only inside one don't
    # score identical (AC 6).
    heading: str | None = None
    structural_tokens: list[str] | None = None


@dataclass
class CapturedForm:
    page_url: str
    action_url: str
    method: str
    fields: list[CapturedFormField] = field(default_factory=list)


@dataclass
class CapturedAction:
    page_url: str
    description: str
    captured_selector: str | None = None
    representative: bool = True
    # Story 2.21: ranked candidate locators — see CapturedFormField.
    locator_candidates: list[dict] | None = None


@dataclass
class CapturedApiCall:
    page_url: str
    method: str
    path: str
    status_code: int | None = None
    response_summary: str | None = None


@dataclass
class CapturedTransition:
    from_url: str
    to_url: str
    triggered_by_description: str | None = None


@dataclass
class CapturedPageComplete:
    """Story 2.10 Task 7: signals that `url`'s full capture set (Page, every
    Action/Form/ApiCall/Transition attributed to it) is now known, so the
    persist layer can classify SAME/VARIANT/NEW with the page's *complete*
    action/form set — not just what was known at first navigation. Emitted
    at the end of the per-page loop body **and every early-exit path**
    (session expiry, mid-crawl reauth retry) — a missed exit path strands
    that page's captures in the buffer permanently."""

    url: str


CapturedItem = (
    CapturedPage
    | CapturedForm
    | CapturedAction
    | CapturedApiCall
    | CapturedTransition
    | CapturedPageComplete
)


@dataclass
class CrawlResult:
    pages: list[CapturedPage] = field(default_factory=list)
    forms: list[CapturedForm] = field(default_factory=list)
    actions: list[CapturedAction] = field(default_factory=list)
    api_calls: list[CapturedApiCall] = field(default_factory=list)
    transitions: list[CapturedTransition] = field(default_factory=list)
    session_expired: bool = False


class _CaptureSink:
    """Fans each captured item out to an optional callback the instant it's
    captured — so a caller (the real Activity) can persist it to Postgres
    immediately, rather than waiting for the whole (possibly very long,
    uncapped per Story 2.3) crawl to finish. Without this, a real site that
    takes longer than an Activity timeout loses every bit already captured
    when the attempt is killed and retried from scratch."""

    def __init__(
        self, result: CrawlResult, on_capture: Callable[[CapturedItem], None] | None
    ) -> None:
        self._result = result
        self._on_capture = on_capture

    async def add(self, item: CapturedItem) -> None:
        if isinstance(item, CapturedPage):
            self._result.pages.append(item)
        elif isinstance(item, CapturedForm):
            self._result.forms.append(item)
        elif isinstance(item, CapturedAction):
            self._result.actions.append(item)
        elif isinstance(item, CapturedApiCall):
            self._result.api_calls.append(item)
        elif isinstance(item, CapturedTransition):
            self._result.transitions.append(item)
        if self._on_capture:
            # `_on_capture` (the real Activity's `_persist`) does a
            # synchronous Postgres commit — off the event loop so a slow
            # commit stalls only this crawl, not the heartbeat/poll loop
            # this worker process owes Temporal for every other concurrent
            # workflow (observed live: a stalled commit froze the whole
            # worker, not just this activity — 2026-07-21).
            await asyncio.to_thread(self._on_capture, item)


def _same_origin(url: str, base_url: str) -> bool:
    return urlparse(url).netloc == urlparse(base_url).netloc


def _is_self_referential_duplicate(url: str, base_url: str) -> bool:
    """`[FIXED 2026-07-23]` Observed live: a client-side router bug on this
    real target (a relative `navigate()` call resolved against the current
    path instead of the app root) produced a genuine browser navigation to
    `.../react-pages/Home/bm_catalog_backoffice_ui/react-pages/Home` — the
    app's own base path glued onto itself. A legitimate page can never
    contain its own app-root path segment twice, so this is a cheap,
    app-name-agnostic tripwire for that whole bug class rather than a fix
    for this one URL."""
    stem = urlparse(base_url).path.strip("/")
    return bool(stem) and urlparse(url).path.count(stem) > 1


# OIDC Authorization Code flow params (RFC 6749/OIDC core) — see
# `_page_fingerprint`'s docstring for why these get stripped.
_OAUTH_CALLBACK_PARAMS = {"code", "state", "session_state", "iss"}


def _page_fingerprint(url: str) -> str:
    """BFS bookkeeping key (AC 4). `[FIXED 2026-07-22]` Only strips a truly
    *empty* fragment, not any fragment — a shared header form whose
    `action="#"` just appends a bare `#` to whatever page you're already on
    when submitted (`.../search?q=x` -> `.../search?q=x#`), and without
    collapsing that specific case the crawler loops forever re-queuing what
    is really the same page.

    A **non-empty** fragment is very often a real, distinct page in a
    hash-routed SPA (`#/orders`, `#!/products`, `#ProductManagement` —
    common in Angular/React apps, including WaveMaker-generated ones). The
    previous version stripped fragments unconditionally, which silently
    merged every hash-routed page in the app into a single BFS node: once
    any one of them was visited, every other one looked "already visited"
    and was never crawled — the root cause of a real run covering only 4 of
    an application's ~10 pages, all reachable only via `#`-routed nav
    (observed live, shopbit.onwavemaker.com, 2026-07-22). Worth a redundant
    re-visit of a same-page scroll anchor (`/about#team`) over silently
    dropping a real page — never the other way around.

    Also strips a bare trailing `?` (empty query string) — a GET form with
    no named fields (that same shared header form) genuinely navigates to
    `url?` when submitted, real browser behavior, not a typo. A real,
    non-empty query string (`.../product?id=6`) is untouched.

    `[FIXED 2026-07-22, again]` Also strips one-time OAuth/OIDC Authorization
    Code flow callback params (`code`/`state`/`session_state`/`iss`) from the
    query string. Observed live against a real Keycloak-backed app: a
    silent-SSO redirect — retriggered by this crawler's own restore-
    after-navigate `page.goto()` calls in `_click_standalone_buttons` —
    lands back on the exact same route but with a FRESH, single-use
    `code`/`state` each time. Left unstripped, every one of those looks like
    a brand-new page: the crawler re-queued and re-captured the same "Home"
    page 3+ times, one button click at a time, and never got past it. These
    params are inherently single-use and never meaningfully distinguish one
    page from another the way a real `?id=6`-style query does."""
    base, fragment = urldefrag(url)
    if base.endswith("?"):
        base = base[:-1]

    split = urlsplit(base)
    if split.query:
        kept_params = [
            (key, value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
            if key not in _OAUTH_CALLBACK_PARAMS
        ]
        base = urlunsplit(split._replace(query=urlencode(kept_params)))

    return f"{base}#{fragment}" if fragment else base


async def _submit_button_label(locator: Locator) -> str | None:
    """`<input type=submit>` shows its label via the `value` attribute, not
    innerText — unlike a `<button>`, so this needs its own lookup rather than
    reusing `_capture_selector`'s fallback_text convention."""
    tag = await locator.evaluate("el => el.tagName.toLowerCase()")
    if tag == "input":
        value = await locator.get_attribute("value")
        return value.strip() if value and value.strip() else None
    text = (await locator.inner_text()).strip()
    return text or None


async def _invalid_field_messages(page: Page | Frame, invalid_fields: Locator) -> list[str]:
    """Resolves each `aria-invalid="true"` field's `aria-describedby` id to
    the referenced element's text — the page's own error copy, not just the
    presence signal `[aria-invalid="true"]` already gives us."""
    messages: list[str] = []
    for i in range(await invalid_fields.count()):
        described_by = await invalid_fields.nth(i).get_attribute("aria-describedby")
        if not described_by:
            continue
        try:
            text = (await page.locator(f"#{described_by}").inner_text()).strip()
        except Exception:
            continue
        if text:
            messages.append(text)
    return messages


async def _mvc_validation_messages(form: Locator, invalid_fields: Locator) -> list[str]:
    """ASP.NET MVC unobtrusive-validation's own convention: the error text
    lives in a `[data-valmsg-for="<field name>"]` span, matched by the
    input's `name` attribute — there's no id reference to resolve, unlike
    `_invalid_field_messages`'s `aria-describedby` lookup."""
    messages: list[str] = []
    for i in range(await invalid_fields.count()):
        name = await invalid_fields.nth(i).get_attribute("name")
        if not name:
            continue
        try:
            text = (
                await form.locator(f'[data-valmsg-for="{name}"]').first.inner_text()
            ).strip()
        except Exception:
            continue
        if text:
            messages.append(text)
    return messages


# Story 2.10 AC 2/6: the heading + structural-shape signals the State
# Identity Engine scores against, computed in one round trip. The
# structural walk descends into open shadow roots (Story 2.14) — without
# that, two states differing only inside one would produce the same token
# list and score identical, exactly the failure AC 6 exists to prevent.
_STATE_SIGNALS_SCRIPT = r"""
() => {
  function describe(el) {
    const role = el.getAttribute('role');
    return role ? el.tagName.toLowerCase() + '[' + role + ']' : el.tagName.toLowerCase();
  }
  function walk(root) {
    const tokens = [];
    root.querySelectorAll('*').forEach((el) => {
      tokens.push(describe(el));
      if (el.shadowRoot) tokens.push(...walk(el.shadowRoot));
    });
    return tokens;
  }
  const h1 = document.querySelector('h1');
  const h2 = document.querySelector('h2');
  const heading = (h1 && h1.innerText.trim())
    || (h2 && h2.innerText.trim())
    || document.title
    || '';
  // Story 2.10 Task 2: fold in how many of this page's tracked shadow
  // hosts (Story 2.14's attachShadow-tracking init script) are closed —
  // genuinely opaque, but their *count* is still an observable structural
  // fact, so two pages differing only in reachability don't fingerprint
  // identically.
  const hosts = window.__discoveryShadowHosts || [];
  let closedCount = 0;
  hosts.forEach((h) => {
    const host = document.querySelector(`[data-discovery-shadow-id="${h.id}"]`);
    if (host && !host.shadowRoot) closedCount++;
  });
  const tokens = walk(document.body);
  if (closedCount > 0) tokens.push('unreachable:closed_shadow_root:' + closedCount);
  return { heading: heading, structuralTokens: tokens };
}
"""


async def _capture_state_signals(page: Page) -> tuple[str, list[str]]:
    """Best-effort — a failure yields an empty heading/token list rather
    than raising, same tolerance as every other capture helper here."""
    try:
        info = await page.evaluate(_STATE_SIGNALS_SCRIPT)
    except Exception:
        return "", []
    tokens = list(info.get("structuralTokens") or [])
    # Story 2.10 Task 2: same reasoning as the closed-shadow-root count
    # above, for the other unreachable-container kind (Story 2.14) —
    # cross-origin frames Playwright can enumerate directly, no JS needed.
    try:
        cross_origin_count = sum(
            1
            for frame in page.frames
            if frame != page.main_frame
            and frame.url not in ("", "about:blank")
            and not _same_origin(frame.url, page.url)
        )
    except Exception:
        cross_origin_count = 0
    if cross_origin_count:
        tokens.append(f"unreachable:cross_origin_frame:{cross_origin_count}")
    return info.get("heading") or "", tokens



async def _fill_and_submit_form(
    page,
    form_selector: str,
    page_url: str,
    sink: _CaptureSink,
    seen_form_signatures: set[tuple[str, str, tuple[tuple[str | None, str | None], ...]]],
    rescan: Callable[[str], Awaitable[int]] | None = None,
    heartbeat: Callable[[], None] | None = None,
    on_diagnostic: DiagnosticCallback | None = None,
    popup_events: list | None = None,
    network_tracker: NetworkActivityTracker | None = None,
    timeout_seconds: float = DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS,
    frame_path: str | None = None,
    data_resolver_pool: dict[str, data_resolver.PoolEntry] | None = None,
    resolution_log: data_resolver.ResolutionLog | None = None,
) -> str | None:
    # A form's fill+submit+settle sequence can itself run close to the
    # heartbeat_timeout window on a slow page — heartbeating here, not just
    # once per page in the outer loop, is what actually prevents a single
    # slow form from silently exhausting the whole activity's heartbeat and
    # triggering a from-scratch retry (see Dev Notes below).
    if heartbeat:
        heartbeat()

    # Story 2.13: deferred imports for the same reason `_click_standalone_
    # buttons` uses them (see its own comment on the crawler/planner/
    # state_identity import cycle) — `data_resolver` only needs
    # `route_template`, but importing `state_identity` here would eventually
    # cycle back through this module too.
    from discovery_worker import data_resolver, state_identity

    pool = data_resolver_pool or {}
    log = resolution_log if resolution_log is not None else data_resolver.ResolutionLog()
    route_family = state_identity.route_template(page_url)
    # (field_key, value) pairs actually used this submit — success feedback
    # (AC 2/3) is recorded against these once the submit's outcome is known.
    resolved_this_submit: list[tuple[str, str]] = []
    # Buffered, not emitted immediately — a `SyntheticDataEntry` needs the
    # real `outcome` (AC 2/3), which isn't known until after the submit.
    pending_synthetic_data: list[dict] = []

    form = page.locator(form_selector)
    action = await form.get_attribute("action") or page.url
    method = (await form.get_attribute("method") or "get").upper()

    # Includes hidden inputs (only submit/button are excluded here) — a form
    # whose `action` is a blank template with the real identity carried in a
    # *hidden field's value* (e.g. Shopbit's per-product "Add to Cart":
    # `action="cart?product-id=&quantity="`, `<input name="product-id"
    # value="6" type="hidden">`) would otherwise look byte-identical across
    # every product and only the first one ever get exercised.
    all_inputs = form.locator("input:not([type=submit]):not([type=button])")
    # One round-trip for every field's starting state, not one per attribute
    # per field — a field-heavy form (a checkout/payment page can easily have
    # a dozen+ inputs) would otherwise multiply into dozens of separate
    # browser round-trips just to decide whether this form was seen before.
    # `checkValidity()` forces the browser to compute `validationMessage` —
    # it's otherwise empty until constraint validation actually runs once.
    input_info = await all_inputs.evaluate_all(
        "els => els.map(el => {"
        "el.checkValidity();"
        "return {"
        "type: el.type || 'text', name: el.name || null, value: el.value || null, "
        "id: el.id || null, required: el.required, accept: el.accept || null, "
        "validationMessage: el.validationMessage || null"
        "};"
        "})"
    )

    # Representative-form sampling: a form's initial state (shape + every
    # input's starting name/value, hidden included) reachable identically
    # from every page — e.g. a shared header search box — is one feature
    # worth capturing once per crawl, not once per page it happens to appear
    # on (mirrors AC 6's button sampling, applied to forms). Any observable
    # difference — including a hidden identifier's value — means these are
    # genuinely different instances, so this stays conservative by design:
    # dedup only fires when nothing at all differs.
    signature = (
        action,
        method,
        tuple((info["name"], info["value"]) for info in input_info),
    )
    if signature in seen_form_signatures:
        logger.info("  skip form on %s: identical signature already seen this crawl", page_url)
        return None
    seen_form_signatures.add(signature)
    logger.info("  filling form on %s: %d fields", page_url, len(input_info))

    fields: list[CapturedFormField] = []
    for i, info in enumerate(input_info):
        if info["type"] == "hidden":
            continue
        # A field-heavy form (checkout/payment) fills one field at a time —
        # each fill is its own browser round-trip, and a slow remote site
        # can make a dozen-plus of these add up past the heartbeat window
        # well before the form is ever submitted. Heartbeat per field, not
        # just once at the top of the whole form.
        if heartbeat:
            heartbeat()
        field_el = all_inputs.nth(i)
        input_type = info["type"]
        name = info["name"]
        if input_type == "file":
            # Story 2.14 AC 6: routed to a placeholder file rather than
            # `_generic_value` — there is no meaningful text value for an
            # upload field.
            path = _placeholder_file_path(info.get("accept"))
            selector = await _capture_selector(field_el, fallback_text=name)
            candidates = await _capture_locator_candidates(
                field_el, fallback_text=name, frame_path=frame_path
            )
            try:
                await field_el.set_input_files(path, timeout=2000)
                fields.append(
                    CapturedFormField(
                        name=name,
                        input_type=input_type,
                        required=info["required"],
                        default_value=os.path.basename(path),
                        captured_selector=selector,
                        locator_candidates=candidates,
                        validation_message=info.get("validationMessage"),
                    )
                )
                if on_diagnostic:
                    await _emit_diagnostic(
                        on_diagnostic,
                        "data_resolution",
                        {
                            "field": name,
                            "type": "file",
                            "resolution": "placeholder_file",
                            "filename": os.path.basename(path),
                        },
                    )
            except Exception:
                pass
            continue
        # Story 2.13 AC 1: five-step resolution — pool, then per-run reuse,
        # then safe synthesis (step 2, page-scanning, is deliberately not
        # built; see `data_resolver`'s module docstring). `_generic_value`
        # (Story 2.2) still supplies step 4's candidate value unchanged —
        # this extends that behaviour, it doesn't replace it (Dev Notes).
        field_name_for_resolution = name or info["id"] or ""
        resolved = data_resolver.resolve(
            field_name=field_name_for_resolution,
            input_type=input_type,
            route_family=route_family,
            pool=pool,
            log=log,
            generic_value=_generic_value(input_type, name, info["id"]),
        )
        if resolved is None:
            if info["required"]:
                # AC 5/6: an unresolvable *required* field defers the whole
                # form-submit action, not just this field — the Planner
                # would attach this to the Blocked Frontier (Story 2.15);
                # not yet built, so this is recorded as a diagnostic in the
                # meantime rather than silently invented or silently lost.
                if on_diagnostic:
                    await _emit_diagnostic(
                        on_diagnostic,
                        "execution_decision",
                        {
                            "url": page_url,
                            "action": "DEFER",
                            "label": field_name_for_resolution,
                            "deciding_specialist": "data_resolver",
                            "reason": (
                                f"unresolved required field "
                                f"{field_name_for_resolution!r}: no pool entry, "
                                "business-specific, not synthesized"
                            ),
                            "normalized_key": data_resolver.field_key(
                                field_name_for_resolution, input_type
                            ),
                        },
                    )
                return None
            # Optional and unresolvable — left unfilled, same as any other
            # field this function already skips via the `except` below.
            continue
        value = resolved.value
        selector = await _capture_selector(field_el, fallback_text=name)
        candidates = await _capture_locator_candidates(
            field_el, fallback_text=name, frame_path=frame_path
        )
        try:
            # Explicit short timeout, not Playwright's 30s default — a
            # checkout-sized form can have several CSS-hidden conditional
            # fields (e.g. a "same as billing" toggle) that never become
            # actionable; without this, each one burns its full default
            # wait before falling into the except below (observed live:
            # ~2.7min silent gap on a 46-field form, 2026-07-20).
            await field_el.fill(value, timeout=2000)
            fields.append(
                CapturedFormField(
                    name=name,
                    input_type=input_type,
                    required=info["required"],
                    default_value=value,
                    captured_selector=selector,
                    locator_candidates=candidates,
                    validation_message=info.get("validationMessage"),
                )
            )
            used_key = data_resolver.field_key(field_name_for_resolution, input_type)
            resolved_this_submit.append((used_key, value))
            # Story 2.13 Task 4: every resolved value gets a
            # `SyntheticDataEntry` row, not only synthesized ones — masked
            # here (before it ever leaves process memory into a diagnostic
            # payload) when the pool marked it sensitive (Story 2.20 AC 6).
            # Emitted after the submit below, once the real `outcome` (AC
            # 2/3) is known, rather than here with a placeholder that would
            # never get corrected.
            pending_synthetic_data.append(
                {
                    "field_name": field_name_for_resolution,
                    "normalized_key": used_key,
                    "value": "***REDACTED***" if resolved.is_sensitive else value,
                    "source": resolved.source,
                    "is_placeholder_file": False,
                    "page_url": page_url,
                }
            )
        except Exception:
            continue

    before_url = _page_fingerprint(page.url)
    submit = form.locator("button[type=submit], input[type=submit], button:not([type])")
    submit_label: str | None = None
    submit_selector: str | None = None
    submit_candidates: list[dict] | None = None
    # Bracket the submit+settle sequence with heartbeats — this is the
    # single slowest step in form processing (a real submit can redirect
    # through an auth check, hit a slow remote server, or reload a
    # multi-asset page) and was the actual observed cause of a whole-crawl
    # heartbeat-timeout retry loop (2026-07-20, checkout.jsp on a real site).
    if heartbeat:
        heartbeat()
    try:
        if await submit.count() > 0:
            submit_label = await _submit_button_label(submit.first)
            submit_selector = await _capture_selector(submit.first, fallback_text=submit_label)
            submit_candidates = await _capture_locator_candidates(
                submit.first, fallback_text=submit_label, frame_path=frame_path
            )
            await submit.first.click(timeout=2000)
        else:
            await form.evaluate("f => f.submit()")
    except Exception:
        pass
    # A real submit can redirect through an auth check or reload a page with
    # dozens of assets — well past a single short navigation-event window —
    # so settle generically (Story 2.9's readiness gate) instead of racing
    # one `expect_navigation` call. A submit with no navigation at all (a
    # client-side "Add to Cart" that only updates in-page state) resolves
    # these near-instantly, so this adds no real delay for that case.
    await wait_for_page_ready(page, timeout_seconds, network_tracker, heartbeat)

    await sink.add(
        CapturedForm(page_url=page_url, action_url=action, method=method, fields=fields)
    )
    # Dialogs/popups are page-level concepts — only checked when `page` is
    # genuinely the top-level Page (not a Frame passed in for Story 2.14's
    # frame-content capture, which has no `.keyboard`/popup concept of its
    # own; a dialog opened from inside a frame still attaches to the page).
    if isinstance(page, Page):
        await _handle_dialog_if_opened(
            page, sink, page_url, submit_label, heartbeat, on_diagnostic
        )
        await _handle_popups(
            popup_events, page_url, sink, before_url, submit_label, on_diagnostic
        )
    after_url = _page_fingerprint(page.url)

    if resolved_this_submit:
        # Story 2.13 AC 2/3: success feedback. `ponytail:` two bounded
        # heuristics, not the fuller "validation error OR no expected
        # transition OR unchanged fingerprint" list Task 3 sketches — a
        # navigating submit is treated as success outright (Dev Notes:
        # don't over-build attribution); only the no-navigation case is
        # checked at all. Upgrade if a pilot shows real forms that reject
        # without ever setting either signal. When several fields were
        # filled in one submit and it's rejected, every one of them is
        # demoted together (Dev Notes' "demote the set" attribution rule) —
        # this function has no way to isolate which single field was at
        # fault.
        outcome = "success"
        rejection_messages: list[str] = []
        if after_url == before_url:
            has_error = False
            try:
                aria_invalid = form.locator('[aria-invalid="true"]')
                if await aria_invalid.count() > 0:
                    has_error = True
                    rejection_messages += await _invalid_field_messages(page, aria_invalid)
            except Exception:
                pass
            try:
                # ASP.NET MVC unobtrusive-validation (jQuery) marks a
                # rejected input with this class and its message in a
                # sibling `[data-valmsg-for="<field name>"]` span, matched
                # by name rather than an id reference — no `aria-invalid`/
                # `aria-describedby` at all. Observed live on a real login
                # form with no ARIA or native constraint-validation markup
                # whatsoever (digitalbankingportal.onwavemaker.com, 2026-08-12).
                mvc_invalid = form.locator(".input-validation-error")
                if await mvc_invalid.count() > 0:
                    has_error = True
                    rejection_messages += await _mvc_validation_messages(form, mvc_invalid)
            except Exception:
                pass
            outcome = "rejected" if has_error else "unknown"
        for used_key, used_value in resolved_this_submit:
            log.record_outcome(used_key, used_value, outcome)
        if on_diagnostic:
            for record in pending_synthetic_data:
                await _emit_diagnostic(
                    on_diagnostic, "synthetic_data", {**record, "outcome": outcome}
                )
            if outcome == "rejected":
                # Task 6: the "values the application rejected" report
                # section reads this — separate from the SyntheticDataEntry
                # row above (Task 4), which already carries `outcome` too,
                # but this is what a rejection-focused query can filter on
                # without joining, and it doesn't need `value` at all
                # (never re-expose it, sensitive or not).
                for used_key, _ in resolved_this_submit:
                    await _emit_diagnostic(
                        on_diagnostic,
                        "data_resolution",
                        {
                            "normalized_key": used_key,
                            "outcome": "rejected",
                            "page_url": page_url,
                            "messages": rejection_messages,
                        },
                    )

    # Recorded whenever there's a real label, whether or not the submit
    # produced a navigation — a submit that only updates in-page state (no
    # URL change, no XHR) is still a real, testable business action; a
    # Transition is the one that needs an actual observed navigation to mean
    # anything.
    if submit_label:
        await sink.add(
            CapturedAction(
                page_url=before_url,
                description=submit_label,
                captured_selector=submit_selector,
                locator_candidates=submit_candidates,
            )
        )
    if after_url != before_url:
        logger.info("  form submit on %s navigated -> %s", page_url, after_url)
        await sink.add(
            CapturedTransition(
                from_url=before_url, to_url=after_url, triggered_by_description=submit_label
            )
        )
    elif rescan:
        # No navigation — but the submit may still have changed the DOM
        # in-place (e.g. an AJAX "Add to Cart" that updates a nav badge, or
        # reveals a confirmation panel with its own links). A one-shot link
        # scrape at page-load time would never see whatever this revealed.
        newly_found = await rescan(before_url)
        if newly_found:
            logger.info(
                "  form submit on %s revealed %d new link(s) without navigating",
                page_url,
                newly_found,
            )
    return after_url if after_url != before_url else None


async def _recover_login_if_needed(
    page,
    expected_url: str,
    credential: bytes | None,
    heartbeat: Callable[[], None] | None = None,
) -> bool:
    """Called after a restore-style `page.goto(expected_url)` (used both
    after a navigating button click and after a form submit, below). Some
    real apps — observed live: a Keycloak-backed one that re-checks auth
    aggressively enough that even a plain restore navigation can land back on
    its login screen — make this restore itself unreliable. Returns True
    once `page` is genuinely back on `expected_url`, attempting a bounded
    number of login replays first if a password field is present and a
    `credential` is available to replay it with. Returns False if recovery
    wasn't possible (no credential, or every retry still didn't land where
    expected) — it's the caller's job to then stop cleanly rather than
    silently keep operating on the wrong page.

    `[FIXED 2026-07-22]` A single attempt here wasn't enough on an app that
    re-checks auth this aggressively — observed live: exploring a left-nav
    sidebar stopped after just 1-2 real items every time, always right after
    the *first* navigating click, because this recovery only ever tried
    once and gave up the moment that one attempt didn't land cleanly (a
    transient Keycloak-redirect timing hiccup, not a truly dead session).
    The outer per-page reauth in `run_discovery_crawl` already tolerates
    this via `_MAX_CONSECUTIVE_REAUTH_ATTEMPTS` retries; this one, called
    far more often (once per click, not once per page), needs the same
    tolerance even more."""
    if _page_fingerprint(page.url) == expected_url:
        return True
    if credential is None:
        return False
    for _attempt in range(_MAX_CONSECUTIVE_REAUTH_ATTEMPTS):
        if await page.locator('input[type="password"]').count() == 0:
            return False
        await attempt_login(page, credential, heartbeat=heartbeat)
        if heartbeat:
            heartbeat()
        try:
            await page.goto(expected_url)
        except Exception:
            return False
        if heartbeat:
            heartbeat()
        if _page_fingerprint(page.url) == expected_url:
            return True
    return False


async def _click_standalone_buttons(
    page,
    sink: _CaptureSink,
    base_url: str,
    rescan: Callable[[str], Awaitable[int]] | None = None,
    heartbeat: Callable[[], None] | None = None,
    credential: bytes | None = None,
    seen_labels: set[str] | None = None,
    on_diagnostic: DiagnosticCallback | None = None,
    popup_events: list | None = None,
    network_tracker: NetworkActivityTracker | None = None,
    timeout_seconds: float = DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS,
    frame_path: str | None = None,
    entry_url: str | None = None,
    loop_guard: planner.SpecialistFn | None = None,
    safety: planner.SpecialistFn | None = None,
    data_resolver: planner.SpecialistFn | None = None,
    loop_guard_state: planner.LoopGuardState | None = None,
    interaction_level: planner.SpecialistFn | None = None,
) -> list[str]:
    """Clicks every distinct-labeled standalone button — page-body content
    tried before nav/header/footer chrome, no numeric cap on either (see the
    comment above `_BODY_BUTTONS`/`_CHROME_BUTTONS`) — and returns any
    same-origin URL reached this way for the caller to enqueue, same as a
    link or form-submit destination.

    `[FIXED 2026-07-22]` A click that navigates away used to stop this
    function entirely, on the theory that remaining locator indices would
    resolve against the new page, not this one — true, but wrong for a
    persistent-shell SPA (e.g. a left-nav sidebar shown on every route):
    once *any* item earlier in DOM order pointed back to a page already
    visited (an extremely common shape — a "Home"/logo link), every visit to
    every *other* page hit that item first, navigated away immediately, and
    never got to try the rest of the sidebar at all (observed live: a 13-item
    left-nav where only 1-2 items were ever reachable). Now restores the
    original page (`page.goto(before_url)`, the same restore-after-navigate
    pattern `_fill_and_submit_form`'s caller already uses for forms below)
    and keeps going — re-querying candidates fresh each pass, so a dropdown
    reveal or a restored page's re-rendered DOM is never read from a stale
    locator. A click that does *not* navigate (a dropdown/drawer/accordion
    toggle) triggers `rescan` the same as before.

    `[ADDED 2026-07-22]` `seen_labels`, if passed in, is mutated in place and
    used as the starting point instead of an empty set — lets the caller
    checkpoint progress across a mid-page session-expiry restart (see
    `seen_button_labels_by_page` in `run_discovery_crawl`), so a retry skips
    straight past already-clicked buttons instead of re-doing them (and
    risking expiring again before ever reaching a new one)."""
    before_url = _page_fingerprint(page.url)
    if seen_labels is None:
        seen_labels = set()
    discovered: list[str] = []
    # `[ADDED 2026-08-05]` Caps the reload-and-retry-once escape hatch below
    # (see its use site) at one attempt per candidate per page visit — a
    # candidate that's still broken after a full reload isn't going to fix
    # itself with a second one, and this bounds it against ever looping.
    reload_retried_labels: set[str] = set()
    # `[ADDED 2026-08-05]` Persists across the whole page visit (every tier/
    # group iteration), not reset per candidate like `is_ambiguous_icon_toggle`
    # below — confirmed live: two different ambiguous-icon candidates both
    # toggle the *same* region (a `document.body.innerText`-based check at
    # click-failure time showed the whole revealed sidebar gone from the page
    # entirely, not merely this one element gone — a double-toggle net
    # collapse, not a stale-handle/re-render problem). Once one of them has
    # confirmed a reveal (grew the candidate count), trying a second one
    # risks re-closing what the first one opened for no benefit — the reveal
    # already happened, so there's nothing left to gain from opening it
    # "again" via a different control.
    revealed_via_icon_toggle = False

    # `state_identity` imports `_page_fingerprint` from this module —
    # deferred imports here, not module-level ones, are what avoid a
    # circular import between the two (and, transitively, `planner`).
    from discovery_worker import planner, state_identity
    from discovery_worker.planner import return_to_state

    # Story 2.19: a real `loop_guard_state` (the crawl-wide bookkeeping
    # instance) takes precedence over a directly-injected `loop_guard`
    # callable — the two are never meant to be supplied together, but the
    # state object is what `run_discovery_crawl` actually passes.
    loop_guard = (loop_guard_state.guard if loop_guard_state else loop_guard) or (
        planner.default_loop_guard
    )
    safety = safety or planner.default_safety
    data_resolver = data_resolver or planner.default_data_resolver

    # Story 2.11 AC 5: captured once, before any click in this call — the
    # State Return ladder's confirmation target for every restore attempt
    # this function makes. Frame-scoped calls (Story 2.14) skip the ladder
    # entirely below (`Frame` has no `go_back()`), so this is skipped too.
    pre_action_fingerprint = None
    if isinstance(page, Page):
        heading, structural_tokens = await _capture_state_signals(page)
        pre_action_fingerprint = state_identity.compute_fingerprint(
            heading, [], [], structural_tokens
        )

    # Story 2.11 AC 1/2: every Tier 1 (in-page) candidate across *both* DOM
    # groups is exhausted before any Tier 2 (navigation-intent) candidate is
    # even attempted — outer tier pass, inner body-then-chrome group, same as
    # before this story. A candidate skipped only because it doesn't match
    # the current tier pass is left off `seen_labels` so it's picked up on
    # the Tier 2 pass; this re-scans the DOM twice as often as the old
    # single-pass loop, a deliberate, bounded cost for correct tiering.
    source_route_template = state_identity.route_template(before_url)
    for tier in (planner.TIER_IN_PAGE, planner.TIER_NAVIGATION):
        for group_selector, group_name in (
            (_BODY_BUTTONS, "body"),
            (_CHROME_BUTTONS, "chrome (nav/header/footer)"),
        ):
            in_landmark = group_name != "body"
            while True:
                buttons = page.locator(group_selector)
                button_count = await buttons.count()
                # Batched: one round trip for every label/role instead of one
                # per candidate — the old per-`.nth(i)` `inner_text()`/
                # `get_attribute()` awaits made each outer pass O(button_count)
                # CDP calls, and this loop runs once per button found on the
                # page, so a page with many buttons paid O(button_count^2)
                # round trips. `all_inner_texts()`/`evaluate_all()` fetch the
                # whole group in one call each; the per-candidate skip logic
                # below is unchanged, just reading from the batched lists.
                try:
                    all_labels = await buttons.all_inner_texts()
                except Exception as exc:
                    logger.info(
                        "  %s: %s button batch inner_text failed, ending %s pass (%s)",
                        before_url,
                        group_name,
                        group_name,
                        exc,
                    )
                    break
                try:
                    all_roles = await buttons.evaluate_all(
                        "els => els.map(el => el.getAttribute('role'))"
                    )
                except Exception:
                    all_roles = [None] * button_count
                try:
                    # A button with no visible text *and* no aria-label/title
                    # (a bare icon-font glyph — e.g. a drawer/hamburger toggle)
                    # would otherwise get `candidate_label == ""` below and be
                    # silently invisible forever: every downstream step keys
                    # off `label` (dedup, action history, safety matching), so
                    # a blank one can never be discovered or clicked. The
                    # icon's own most-specific class name (e.g. "wi-menu") is
                    # a stable substitute distinct per icon; repeated
                    # instances of the same icon (e.g. one "..." row-menu per
                    # grid row) collapse to the same synthetic label, which is
                    # exactly what Representative-action sampling below
                    # already wants for a repeated control. Prefixed so it's
                    # never confused with real DOM text (see `_ICON_LABEL_PREFIX`
                    # use at the selector-capture call site below).
                    all_icon_labels = await buttons.evaluate_all(
                        """els => els.map(el => {
                            const aria = (el.getAttribute('aria-label') || '').trim();
                            if (aria) return aria;
                            const title = (el.getAttribute('title') || '').trim();
                            if (title) return title;
                            const iconEl = el.matches('i[class]') ? el : el.querySelector('i[class]');
                            const cls = iconEl
                                ? (iconEl.getAttribute('class') || '').trim().split(/\\s+/).pop()
                                : '';
                            return cls ? ('icon:' + cls) : '';
                        })"""
                    )
                except Exception:
                    all_icon_labels = [""] * button_count
                try:
                    # Disambiguator for the specific case where the real
                    # visible text is itself a bare, generic word like "Icon"
                    # — unlike a truly blank label (handled above, where
                    # collapsing identical icons together is the *desired*
                    # Representative-action sampling behaviour, e.g. one "..."
                    # per grid row), a literal "Icon" text label has been
                    # observed live to belong to two genuinely different
                    # controls on the same page (a hidden drawer toggle and,
                    # separately, something near the profile menu) that
                    # happen to share that exact word — deduping them
                    # together starves whichever is scanned second forever.
                    # `id` is a real, stable identity when present; the DOM
                    # index is a same-scan-only fallback, which is enough to
                    # tell two simultaneously-present anonymous elements apart
                    # without it needing to survive a reload.
                    all_element_ids = await buttons.evaluate_all(
                        "els => els.map(el => el.id || '')"
                    )
                except Exception:
                    all_element_ids = [""] * button_count

                button = None
                label: str | None = None
                role: str | None = None
                is_ambiguous_icon_toggle = False
                for i in range(button_count):
                    if heartbeat:
                        heartbeat()
                    real_text = (all_labels[i] if i < len(all_labels) else "").strip()
                    candidate_label = real_text
                    if not candidate_label:
                        candidate_label = (
                            all_icon_labels[i] if i < len(all_icon_labels) else ""
                        ).strip()
                    candidate_is_ambiguous_icon = real_text.lower() == "icon"
                    if candidate_is_ambiguous_icon:
                        disambiguator = (
                            all_element_ids[i] if i < len(all_element_ids) else ""
                        ) or str(i)
                        candidate_label = f"{real_text}#{disambiguator}"
                    # Representative-action sampling (AC 6): a repeated identical
                    # action pattern (e.g. one "Edit" button per grid row) is
                    # exercised once, not once per DOM instance. Scoped by
                    # `group_name` (body vs. chrome), not bare label — apps
                    # reuse the same generic accessible name (e.g. a header
                    # hamburger and every per-row grid "..." action menu both
                    # reporting `aria-label="Menu"`) for controls that are not
                    # duplicates of each other at all; without this, whichever
                    # one is scanned first (body, always before chrome) wins
                    # and permanently shadows the other for this whole page
                    # visit, same failure mode representative sampling exists
                    # to avoid, not cause.
                    seen_key = f"{group_name}\x00{candidate_label}"
                    if not candidate_label or seen_key in seen_labels:
                        continue
                    if candidate_is_ambiguous_icon and revealed_via_icon_toggle:
                        # `[ADDED 2026-08-05]` A different ambiguous-icon
                        # candidate already confirmed a reveal this page visit
                        # (see `revealed_via_icon_toggle`'s definition) — the
                        # nav is open; clicking a second icon-toggle control
                        # risks being the same drawer's close action reached a
                        # different way, undoing it for zero gain.
                        seen_labels.add(seen_key)
                        continue
                    # `[CHANGED 2026-08-04]` A prior fix unconditionally
                    # skipped any bare, generic "Icon" label (no other
                    # distinguishing text) — observed live on some other app:
                    # it was a left-nav *collapse* toggle, clicking it
                    # genuinely collapsed an already-open sidebar to zero
                    # size for the rest of the page visit. But the same bare
                    # "Icon" accessible name is exactly as likely to be a
                    # left-nav *reveal* toggle instead (observed live on a
                    # WaveMaker admin app: its list-view pages render the
                    # sidebar collapsed by default — every section link
                    # behind it, e.g. 10+ catalog categories, was
                    # unreachable — and this exact button is what opens it).
                    # A blanket skip always loses the second case; blanket-
                    # allowing (tried first) always loses the first — it
                    # regressed the original incident, confirmed live: this
                    # exact button on this exact app's *Home* page collapsed
                    # an already-open sidebar. The actual fix is below, after
                    # the click: verify whether the group's own candidate
                    # count grew or shrank, and reload to undo if it shrank.
                    # Still no special-casing of *whether to try* it — it
                    # flows through tiering/safety/dedup like anything else.
                    if _LOGOUT_RE.search(candidate_label):
                        logger.info(
                            "  %s: refusing to click %s button %r — looks like a logout control",
                            before_url,
                            group_name,
                            candidate_label,
                        )
                        seen_labels.add(seen_key)
                        continue
                    # Story 2.11 AC 1: role="tab" is always Tier 1 regardless
                    # of landmark position, so a tab strip that happens to
                    # live inside <nav> still gets exhausted in the Tier 1
                    # pass, not deferred behind every other nav destination.
                    role = all_roles[i] if i < len(all_roles) else None
                    candidate_tier = planner.classify_tier(
                        planner.ActionCandidate(
                            label=candidate_label,
                            role=role,
                            in_landmark=in_landmark,
                            source_route_template=source_route_template,
                            # This function's selectors (_BODY_BUTTONS/
                            # _CHROME_BUTTONS) only ever match a <button> or a
                            # dead-href <a> (see _DEAD_HREF) — a real
                            # route-changing href is always found via the
                            # plain link scrape instead, never here.
                            target_route_template=None,
                        )
                    )
                    if candidate_tier != tier:
                        continue
                    button, label = buttons.nth(i), candidate_label
                    is_ambiguous_icon_toggle = candidate_is_ambiguous_icon
                    break

                if button is None or label is None:
                    # Nothing left unseen (in this tier) in this group — move
                    # to the next group, or the next tier once both groups
                    # are exhausted for it.
                    break

                # `[FIXED 2026-08-05]` `button` is a live `Locator` — every
                # action on it re-runs `group_selector` and re-picks whatever
                # is *currently* at index `i`, not the specific element just
                # scanned above. Confirmed live: a real, always-visible sidebar
                # link (`getBoundingClientRect()` non-zero, `visibility:
                # visible`, checked directly) still measured a (0,0,0,0) rect
                # at the exact moment `button.click()` ran, for 68 straight
                # candidates across repeated runs — the several awaits between
                # picking this candidate and clicking it (state-signal capture,
                # selector capture, locator-candidate capture) are enough time
                # for this app's own re-renders to reorder/remount the list out
                # from under a position-based lookup. `element_handle()` pins
                # the actual DOM node chosen above; clicking that instead of
                # re-resolving by position is immune to the list changing
                # shape in between. Only the click itself needs this — the
                # selector/candidate-capture calls below stay on `button`
                # (the descriptive `Locator` API), since they're for reporting,
                # not for identifying what gets clicked.
                seen_labels.add(seen_key)

                button_handle = await button.element_handle()
                if button_handle is None:
                    # Vanished between being scanned and now — nothing to
                    # click, and no point misattributing this as a visibility
                    # failure. Already in `seen_labels` above, so this doesn't
                    # loop forever re-picking the same vanished candidate.
                    continue

                # Story 2.11 AC 3/4/7: exactly one Execution Decision per
                # candidate, before it runs — loop guards, then safety, then
                # the data resolver (default pass-throughs today; Stories
                # 2.19/2.12/2.13 replace them without touching this call site).
                # `state_key=before_url`: the specific state instance this
                # candidate is tried from (Story 2.19 AC 2a) — distinct from
                # `source_route_template`, the route *family* AC 2c operates
                # on across parameterized pages.
                action_candidate = planner.ActionCandidate(
                    label=label,
                    role=role,
                    in_landmark=in_landmark,
                    source_route_template=source_route_template,
                    target_route_template=None,
                    state_key=before_url,
                )
                decision = planner.decide(
                    action_candidate,
                    loop_guard=loop_guard,
                    safety=safety,
                    data_resolver=data_resolver,
                    interaction_level=interaction_level,
                )
                # Story 2.12 AC 6: one diagnostic per safety verdict actually
                # reached — `deciding_specialist == "loop_guard"` means safety
                # was never even asked (loop guards run first), so there's no
                # verdict to record. `safety` is a `SafetyState` instance only
                # when the real engine (not a pass-through/test stub) is
                # wired in.
                safety_verdict = getattr(safety, "last_verdict", None)
                if decision.deciding_specialist != "loop_guard" and safety_verdict is not None:
                    if on_diagnostic:
                        await _emit_diagnostic(
                            on_diagnostic,
                            "safety_verdict",
                            {
                                "url": before_url,
                                "label": label,
                                "matched_list": safety_verdict.matched_list,
                                "posture": safety_verdict.posture,
                                "ai_consulted": safety_verdict.ai_consulted,
                                "verdict": safety_verdict.verdict,
                            },
                        )
                if decision.action != "EXECUTE":
                    logger.info(
                        "  %s: %s button %r %s (%s: %s)",
                        before_url,
                        group_name,
                        label,
                        decision.action,
                        decision.deciding_specialist,
                        decision.reason,
                    )
                    if on_diagnostic:
                        payload = {
                            "url": before_url,
                            "action": decision.action,
                            "label": label,
                            "deciding_specialist": decision.deciding_specialist,
                            "reason": decision.reason,
                        }
                        if decision.action == "DEFER":
                            # Story 2.15 Task 3: the Blocked Frontier attaches
                            # on this key — real route family (not the
                            # wildcard `data_resolver.field_key` uses), since
                            # an approval need is inherently route-scoped
                            # (Dev Notes: "Submit" on a claims page and
                            # "Submit" on a settings page are not the same
                            # ask).
                            payload["normalized_key"] = aggregation_key(
                                label, "action_approval", source_route_template
                            )
                        await _emit_diagnostic(on_diagnostic, "execution_decision", payload)
                    continue

                if loop_guard_state:
                    loop_guard_state.record_executed(action_candidate)
                # Story 2.12 Task 4/AC 5: only a genuinely Safe-classified
                # action (not an Ambiguous one merely allowed to execute by
                # non_production posture) gets a before/after check — reuses
                # the same heading/structural-token capture the State
                # Identity Engine already does, no new capture mechanism.
                # Skipped for frame-scoped calls (no `Page.url` restore
                # semantics to compare against) and when the safety engine
                # isn't wired in at all.
                verify_safe_action = (
                    isinstance(page, Page)
                    and safety_verdict is not None
                    and safety_verdict.matched_list == "safe"
                )
                before_signals = None
                if verify_safe_action:
                    before_signals = await _capture_state_signals(page)
                # `[MOVED 2026-08-04, REVERTED 2026-08-05]` Briefly moved
                # after the click, on the theory that fewer awaits between
                # "picked" and "clicked" would help — it didn't (the actual
                # cause was `_visible_content_size`'s bug, see its docstring),
                # and moving it after the click introduced a real regression:
                # once the drawer correctly stayed open, the body group's
                # candidate count legitimately grew past 100, and re-resolving
                # `button` by its original index *after* the click (rather
                # than right after it was chosen) hit a real element at a
                # since-shifted index, timing out `get_attribute` for 30s and
                # crashing the whole run uncaught. Back to capturing
                # immediately after selection, before anything else can move
                # the index out from under it.
                selector_fallback_text = (
                    None
                    if is_ambiguous_icon_toggle or label.startswith(_ICON_LABEL_PREFIX)
                    else label
                )
                selector = await _capture_selector(button, fallback_text=selector_fallback_text)
                candidates = await _capture_locator_candidates(
                    button, fallback_text=selector_fallback_text, frame_path=frame_path
                )
                # `[FIXED 2026-08-05]` Used to be captured only for ambiguous-
                # icon candidates — but a plainly-labeled accordion header
                # (e.g. "Catalog") reveals its children exactly the same way
                # an icon toggle does, and those children got no settle-wait
                # at all: confirmed live, 68 straight `initial_click_not_
                # onscreen` failures on a real app, every one of them a just-
                # revealed submenu item, none of them an icon toggle. Grow/
                # shrink detection below now applies to every non-navigating
                # click, not just icon ones.
                visible_size_before_click = await _visible_content_size(page)
                try:
                    await button_handle.click(timeout=1000)
                except Exception as first_exc:
                    # `[FIXED 2026-07-22]` Observed live: the *exact* same
                    # element, same selector, sometimes fails this click with
                    # "element is not visible" and sometimes succeeds instantly
                    # on a fresh page that never triggered it. Playwright's own
                    # `bounding_box()` isn't a useful independent check here —
                    # it shares the same visibility heuristic the click itself
                    # uses, so it reports zero-size for the exact same reason
                    # the click failed (confirmed live: always empty in exactly
                    # this situation). A raw `getBoundingClientRect()` — real
                    # layout, no Playwright opinion involved — showed this
                    # element fully on-screen with real dimensions the whole
                    # time. This is a left-nav panel's CSS transition class
                    # ("slide-in"/"collapsed") confusing Playwright's stability
                    # check, not a genuinely hidden or covered element, so force
                    # through it — a truly zero-size/off-screen element still
                    # gets skipped below, since the raw rect check catches that
                    # case for real.
                    async def _capture_rect() -> dict | None:
                        try:
                            return await button_handle.evaluate(
                                "el => { const r = el.getBoundingClientRect(); "
                                "return {x: r.x, y: r.y, width: r.width, height: r.height, "
                                "connected: el.isConnected, "
                                "displayNone: window.getComputedStyle(el).display === 'none', "
                                "ancestorWidth: (el.offsetParent ? el.offsetParent.getBoundingClientRect().width : null)}; }"
                            )
                        except Exception:
                            return None

                    async def _text_still_present_anywhere() -> bool | None:
                        # `[ADDED 2026-08-04]` Distinguishes the two candidate
                        # explanations for a zero rect: text findable nowhere
                        # in `document.body.innerText` (which excludes hidden
                        # elements) means the whole region got hidden again
                        # after this candidate was scanned — a different
                        # ambiguous-icon toggle click closing what an earlier
                        # one opened is the leading suspect; text still
                        # present means this specific element is genuinely
                        # stale/detached while its sibling content survives,
                        # pointing at a re-render swapping this one node.
                        search_text = None
                        if is_ambiguous_icon_toggle:
                            search_text = label.split("#", 1)[0]
                        elif not label.startswith(_ICON_LABEL_PREFIX):
                            search_text = label
                        if not search_text:
                            return None
                        try:
                            return await page.evaluate(
                                "t => document.body.innerText.includes(t)", search_text
                            )
                        except Exception:
                            return None

                    rect = await _capture_rect()
                    has_real_size = bool(rect) and rect["width"] > 0 and rect["height"] > 0
                    # `[CHANGED 2026-08-05]` A rect of *exactly* (0,0,0,0) —
                    # not just small, all four fields zero — is the signature
                    # of a detached DOM node: this exact element's text was
                    # read correctly moments earlier (the batched scan above),
                    # so it existed then; a sibling widget's async data
                    # arriving and re-rendering a shared ancestor (observed
                    # live: this app's Home dashboard card loads its content
                    # behind a spinner) can unmount-and-remount the whole
                    # layout region around it in between. `button_handle` now
                    # pins the specific node chosen at scan time (see its
                    # capture above) rather than a live/lazy `Locator` that
                    # re-resolves by position on every action — re-clicking
                    # the *same* handle after a brief wait catches the case
                    # where this node itself was just mid-layout and has
                    # since settled, without the earlier position-based retry
                    # risking a silent hit on a since-shifted, unrelated node.
                    # `[CHANGED 2026-08-05]` A single 400ms wait wasn't the
                    # right order of magnitude — confirmed live: this
                    # particular app can take 3-6+ seconds to finish
                    # re-rendering its nav after a full navigation (initial
                    # login *and* a State Return ladder's `page.goto()` back
                    # to a prior page both go through it), varying run to
                    # run. Backing off across a few retries covers that
                    # range without paying the full ~5s tax on every normal,
                    # fast-rendering candidate — most still resolve on the
                    # first try.
                    retry_click_succeeded = False
                    if not has_real_size and rect == {"x": 0, "y": 0, "width": 0, "height": 0}:
                        for retry_wait_ms in (400, 800, 1600, 2200, 2500, 2500):
                            await page.wait_for_timeout(retry_wait_ms)
                            rect = await _capture_rect()
                            has_real_size = bool(rect) and rect["width"] > 0 and rect["height"] > 0
                            if has_real_size:
                                break
                        if has_real_size:
                            try:
                                await button_handle.click(timeout=1000)
                                retry_click_succeeded = True
                            except Exception:
                                has_real_size = False
                    if not has_real_size:
                        # `[ADDED 2026-08-05]` `rect`'s extra fields (added
                        # alongside this same-day fix) distinguish a specific
                        # case: `connected: true` + `displayNone: false` on
                        # the element itself, but `ancestorWidth: null` (i.e.
                        # `offsetParent` is `null`) — confirmed live, this is
                        # an *ancestor* container collapsed out of layout
                        # (this app's left-nav drawer, after an earlier
                        # candidate's click toggled it shut), not this element
                        # itself being hidden or detached. Every backoff/retry
                        # above already proved this specific signature never
                        # self-heals by waiting longer — the only thing that's
                        # ever restored it live is a full page reload (same
                        # mechanism the shrink-detected-reload path already
                        # uses successfully). One attempt per candidate: undo
                        # via reload, drop it from `seen_labels` so the next
                        # scan re-discovers it fresh (a new `button_handle` —
                        # the reload invalidated this one), and let the outer
                        # loop retry it instead of recording a permanent miss.
                        ancestor_collapsed = (
                            bool(rect)
                            and rect.get("connected") is True
                            and rect.get("displayNone") is False
                            and rect.get("ancestorWidth") is None
                        )
                        if ancestor_collapsed and seen_key not in reload_retried_labels:
                            reload_retried_labels.add(seen_key)
                            logger.info(
                                "  %s: %s button %r looks ancestor-collapsed — "
                                "reloading once to retry it fresh",
                                before_url,
                                group_name,
                                label,
                            )
                            try:
                                await page.goto(before_url)
                                await wait_for_page_ready(
                                    page, timeout_seconds, network_tracker, heartbeat
                                )
                                for recover_wait_ms in (500, 1000, 1500, 2000, 2500, 2500):
                                    if (
                                        await _visible_content_size(page)
                                        >= visible_size_before_click
                                    ):
                                        break
                                    await page.wait_for_timeout(recover_wait_ms)
                                seen_labels.discard(seen_key)
                                continue
                            except Exception as exc:
                                logger.warning(
                                    "  %s: could not reload to retry ancestor-"
                                    "collapsed %r — recording as a miss (%s)",
                                    before_url,
                                    label,
                                    exc,
                                )
                        logger.info(
                            "  %s: %s button click failed, not on-screen: %r (%s)",
                            before_url,
                            group_name,
                            label,
                            first_exc,
                        )
                        # Diagnostic-only (Dev Notes-equivalent: same tolerance
                        # as every other capture helper here) — persisted, not
                        # just `logger.info`'d, so a live failure like this one
                        # is inspectable after the fact instead of needing a
                        # re-run with a debugger attached. `rect` distinguishes
                        # a genuinely zero-size element from one that's real-
                        # sized but positioned off-screen (e.g. still mid a
                        # `transform: translateX` reveal transition).
                        if on_diagnostic:
                            await _emit_diagnostic(
                                on_diagnostic,
                                "click_failure",
                                {
                                    "url": before_url,
                                    "group": group_name,
                                    "label": label,
                                    "stage": "initial_click_not_onscreen",
                                    "error": repr(first_exc)[:500],
                                    "rect": rect,
                                    "text_still_present_anywhere": await _text_still_present_anywhere(),
                                },
                            )
                        continue
                    if not retry_click_succeeded:
                        try:
                            await button_handle.click(timeout=1500, force=True)
                        except Exception as exc:
                            logger.info(
                                "  %s: %s button click failed even with force=True: %r (%s)",
                                before_url,
                                group_name,
                                label,
                                exc,
                            )
                            if on_diagnostic:
                                await _emit_diagnostic(
                                    on_diagnostic,
                                    "click_failure",
                                    {
                                        "url": before_url,
                                        "group": group_name,
                                        "label": label,
                                        "stage": "force_click_failed",
                                        "error": repr(exc)[:500],
                                        "rect": rect,
                                        "text_still_present_anywhere": await _text_still_present_anywhere(),
                                    },
                                )
                            continue
                # Bracket the settle wait too — the click itself is fast, but
                # what it triggers (a redirect, a slow page reload) is the same
                # class of risk `_fill_and_submit_form`'s submit+settle is; Story
                # 2.9's readiness gate replaces the three ad-hoc waits this used.
                await wait_for_page_ready(page, timeout_seconds, network_tracker, heartbeat)
                await sink.add(
                    CapturedAction(
                        page_url=before_url,
                        description=label,
                        captured_selector=selector,
                        locator_candidates=candidates,
                    )
                )
                if isinstance(page, Page):
                    await _handle_dialog_if_opened(
                        page, sink, before_url, label, heartbeat, on_diagnostic
                    )
                    await _handle_popups(
                        popup_events, before_url, sink, before_url, label, on_diagnostic
                    )
                after_url = _page_fingerprint(page.url)
                if after_url != before_url:
                    logger.info(
                        "  %s button %r navigated: %s -> %s",
                        group_name,
                        label,
                        before_url,
                        after_url,
                    )
                    await sink.add(
                        CapturedTransition(
                            from_url=before_url, to_url=after_url, triggered_by_description=label
                        )
                    )
                    if loop_guard_state:
                        loop_guard_state.record_transition(before_url, after_url, label)
                    if _same_origin(after_url, base_url):
                        discovered.append(after_url)

                    if pre_action_fingerprint is None:
                        # Frame-scoped call (Story 2.14) — no ladder (`Frame`
                        # has no `go_back()`), same single-attempt restore as
                        # before this story.
                        try:
                            await page.goto(before_url)
                        except Exception as exc:
                            logger.warning(
                                "  %s: could not restore frame content after %s button %r "
                                "navigated away (%s) — stopping %s group early",
                                before_url,
                                group_name,
                                label,
                                exc,
                                group_name,
                            )
                            break
                        continue

                    async def _settle() -> None:
                        await wait_for_page_ready(page, timeout_seconds, network_tracker, heartbeat)
                        # A rung that lands on a login page (session expiry
                        # mid-click) recovers here, same as before this story —
                        # folded into settle so every rung benefits, not just
                        # the one the old code special-cased.
                        await _recover_login_if_needed(page, before_url, credential, heartbeat)

                    # Story 2.11 AC 5/6: the State Return ladder, replacing the
                    # single-attempt restore this file used before this story.
                    return_result = await return_to_state(
                        page,
                        pre_action_fingerprint,
                        before_url,
                        _capture_state_signals,
                        _settle,
                        entry_url=entry_url,
                    )
                    if heartbeat:
                        heartbeat()
                    if return_result.succeeded:
                        # `[ADDED 2026-08-05]` `return_to_state`'s own match
                        # check (`planner.return_to_state`) only verifies a
                        # heading/structural-token fingerprint — enough to
                        # confirm "the right page's main content is back",
                        # but blind to a nav/sidebar that a lighter-weight
                        # rung (rung 2, `page.go_back()`) can leave broken.
                        # Confirmed live: this app's sidebar never properly
                        # re-mounts on browser-back — every candidate after
                        # a successful-by-fingerprint `browser_back` return
                        # measured a permanent zero rect, even though nothing
                        # here ever detected a click-triggered shrink (that
                        # path never fired — the break was always this one).
                        # `visible_size_before_click` is this same page's own
                        # last-known-good size, captured right before the
                        # click that navigated away from it — reuse it as the
                        # recovery target instead of threading a new baseline
                        # through.
                        recovered_size = await _visible_content_size(page)
                        for return_wait_ms in (500, 1000, 1500, 2000, 2500, 2500):
                            if recovered_size >= visible_size_before_click:
                                break
                            await page.wait_for_timeout(return_wait_ms)
                            recovered_size = await _visible_content_size(page)
                        if recovered_size < visible_size_before_click:
                            # Still short — the fingerprint-matched rung
                            # (typically `browser_back`) left real content
                            # missing. A genuine full re-navigation (rung 3's
                            # own mechanism) is the one path confirmed live to
                            # always fully remount this app; force it here
                            # rather than trusting a return that measurably
                            # isn't whole.
                            try:
                                await page.goto(before_url)
                                await _settle()
                                for return_wait_ms in (500, 1000, 1500, 2000, 2500, 2500):
                                    recovered_size = await _visible_content_size(page)
                                    if recovered_size >= visible_size_before_click:
                                        break
                                    await page.wait_for_timeout(return_wait_ms)
                            except Exception:
                                pass
                        if on_diagnostic:
                            await _emit_diagnostic(
                                on_diagnostic,
                                "state_return",
                                {
                                    "url": before_url,
                                    "rung": return_result.rung,
                                    "attempts_used": return_result.attempts_used,
                                    "opener": label,
                                    "recovered_size": recovered_size,
                                    "expected_size": visible_size_before_click,
                                },
                            )
                        if loop_guard_state:
                            # Story 2.19 AC 2b: the ladder's own successful
                            # restore is the return half of a round trip —
                            # without recording it too, the edge log would
                            # only ever see the forward direction repeated,
                            # and a genuine A->B->A->B oscillation could
                            # never be distinguished from it.
                            loop_guard_state.record_transition(after_url, before_url, label)
                        continue

                    # AC 6: rung 5 — give up honestly. Remaining untried
                    # candidates in this group are `unreached`, not silently
                    # dropped, and the run continues at the next frontier item.
                    if on_diagnostic:
                        await _emit_diagnostic(
                            on_diagnostic,
                            "unreached",
                            {
                                "url": before_url,
                                "reason": "return_failed",
                                "last_rung_attempted": return_result.rung,
                                "attempts_used": return_result.attempts_used,
                                "opener": label,
                                "group": group_name,
                            },
                        )
                    logger.warning(
                        "  %s: state return ladder exhausted after %s button %r navigated away — "
                        "remaining %s candidates are unreached",
                        before_url,
                        group_name,
                        label,
                        group_name,
                    )
                    break
                if before_signals is not None:
                    # Story 2.12 Task 4/AC 5: reached only when the click did
                    # not navigate (the `if after_url != before_url:` block
                    # above always `continue`s or `break`s) — an unexpectedly
                    # large state change right here means a "Safe" action had
                    # a real, visible side effect. Visibility only: recorded
                    # and the crawl continues unconditionally, never blocked
                    # or rolled back.
                    after_heading, after_tokens = await _capture_state_signals(page)
                    before_fingerprint = state_identity.compute_fingerprint(
                        before_signals[0], [], [], before_signals[1]
                    )
                    after_fingerprint = state_identity.compute_fingerprint(
                        after_heading, [], [], after_tokens
                    )
                    anomaly_score = state_identity.score(before_fingerprint, after_fingerprint)
                    if anomaly_score.composite < state_identity.DEFAULT_THRESHOLD_SAME:
                        logger.info(
                            "  %s: Safe button %r produced an unexpected state change "
                            "(composite=%.2f) — recording as a safety anomaly",
                            before_url,
                            label,
                            anomaly_score.composite,
                        )
                        if on_diagnostic:
                            await _emit_diagnostic(
                                on_diagnostic,
                                "safety_anomaly",
                                {
                                    "url": before_url,
                                    "label": label,
                                    "composite_score": anomaly_score.composite,
                                },
                            )
                # `[CHANGED 2026-08-05]` Was gated to `is_ambiguous_icon_toggle`
                # only — generalized to every non-navigating click (see
                # `visible_size_before_click`'s comment above for why: a
                # plain-text accordion header reveals/collapses its children
                # exactly like an icon toggle does, and needs the same
                # shrink-undo and reveal-settle handling).
                # A bare "Icon" label was the original motivating case (it's
                # genuinely ambiguous: on one app it's a *collapse* toggle —
                # an already-open sidebar, clicking it hid everything and it
                # never came back; on another it's a *reveal* toggle — a
                # collapsed-by-default sidebar, clicking it is the only way to
                # reach 10+ nav sections otherwise invisible to this whole
                # crawl). Blanket-skipping always loses the second case;
                # blanket-allowing always loses the first. Check instead: did
                # the page's visible content grow or shrink? Shrink means it
                # just destroyed access to whatever was there before this
                # click — reload to undo, same restore already used for a
                # failed State Return rung, and don't try it again this page
                # visit.
                visible_size_after_click = await _visible_content_size(page)
                if visible_size_after_click < visible_size_before_click:
                    logger.info(
                        "  %s: %s button %r shrank visible content "
                        "(%d -> %d chars) — reloading to undo",
                        before_url,
                        group_name,
                        label,
                        visible_size_before_click,
                        visible_size_after_click,
                    )
                    try:
                        await page.goto(before_url)
                        await wait_for_page_ready(
                            page, timeout_seconds, network_tracker, heartbeat
                        )
                        # `[ADDED 2026-08-05]` `wait_for_page_ready` checks
                        # network-quiet/DOM-stable/content-present, not "this
                        # specific app's nav has actually re-rendered" — this
                        # app has been confirmed live to take 3-9+ seconds to
                        # rehydrate its nav after a full reload, so treating
                        # `wait_for_page_ready` as sufficient here left every
                        # candidate on the *next* attempt at this page zero-
                        # size, permanently, for the rest of the run. Poll
                        # `_visible_content_size` back up towards (not
                        # necessarily past — a reload can legitimately land
                        # on a slightly different byte count) its pre-click
                        # baseline before resuming the scan.
                        recovered_size = visible_size_after_click
                        for reload_wait_ms in (500, 1000, 1500, 2000, 2500, 2500):
                            recovered_size = await _visible_content_size(page)
                            if recovered_size >= visible_size_before_click:
                                break
                            await page.wait_for_timeout(reload_wait_ms)
                        if on_diagnostic:
                            await _emit_diagnostic(
                                on_diagnostic,
                                "shrink_reload",
                                {
                                    "url": before_url,
                                    "group": group_name,
                                    "label": label,
                                    "before": visible_size_before_click,
                                    "after_click": visible_size_after_click,
                                    "recovered": recovered_size,
                                },
                            )
                    except Exception as exc:
                        logger.warning(
                            "  %s: could not reload after undoing %r — stopping "
                            "%s group early (%s)",
                            before_url,
                            label,
                            group_name,
                            exc,
                        )
                        break
                    continue
                if visible_size_after_click > visible_size_before_click:
                    # Grew — a reveal, not a collapse. `wait_for_page_ready`
                    # (just above, before this block) checks network-quiet/
                    # DOM-stable/content-present, none of which cover a
                    # pure CSS transition (a drawer/accordion opening changes
                    # no network activity and no DOM structure, just computed
                    # style over time) — the newly revealed items can still
                    # be mid-slide, genuinely zero/partial-size for a
                    # moment, exactly the class of intermittent failure the
                    # click retry above already exists for, just triggered
                    # differently. A short, bounded wait here is cheap insurance
                    # against attempting the very next candidate while
                    # this one's reveal is still animating.
                    await page.wait_for_timeout(300)
                    revealed_via_icon_toggle = True
                if rescan:
                    # Didn't navigate — likely a toggle/dropdown/drawer/accordion.
                    # Whatever it revealed may include new <a href> nav links
                    # (React/Angular apps very often conditionally *render* menu
                    # items rather than just CSS-hiding a pre-rendered menu, so a
                    # one-shot link scrape at page-load time would never see
                    # them) — this is exactly the gap that hid an app's
                    # authenticated nav menu (Order History, Product Management,
                    # etc.) behind an "Account" dropdown, 2026-07-22.
                    newly_found = await rescan(before_url)
                    if newly_found:
                        logger.info(
                            "  %s button %r revealed %d new link(s) without navigating",
                            group_name,
                            label,
                            newly_found,
                        )
    return discovered


# `[ADDED 2026-07-22]` A genuinely broken login (wrong stored credential,
# a login form the crawler can't drive) must still terminate as
# `session_expired` rather than retry forever — bounds *consecutive*
# re-login attempts with no successful page captured in between (reset to 0
# on every real page, so a long healthy crawl that occasionally needs to
# refresh a short-lived token is never penalized for it).
_MAX_CONSECUTIVE_REAUTH_ATTEMPTS = 3

# Story 2.18 AC 2: a small bounded retry before a 5xx/unreachable
# destination is written as a DiscoveryError (DISC-003) — the source
# document's own example ("e.g. 2").
_MAX_NAV_RETRIES = 2


async def run_discovery_crawl(
    context: BrowserContext,
    base_url: str,
    object_store,
    discovery_run_id: uuid.UUID,
    *,
    on_capture: Callable[[CapturedItem], None] | None = None,
    heartbeat: Callable[[], None] | None = None,
    auth_method: str | None = None,
    credential: bytes | None = None,
    login_page_url: str | None = None,
    on_diagnostic: DiagnosticCallback | None = None,
    max_frame_depth: int = DEFAULT_MAX_FRAME_DEPTH,
    page_load_timeout_seconds: float = DEFAULT_PAGE_LOAD_TIMEOUT_SECONDS,
    max_pages: int | None = None,
    max_duration_seconds: float | None = None,
    interaction_level: str = "normal",
    data_resolver_pool: dict[str, data_resolver.PoolEntry] | None = None,
    safety: planner.SpecialistFn | None = None,
    already_confirmed_urls: frozenset[str] | None = None,
    resume_seed: list[tuple[str, str | None]] | None = None,
) -> CrawlResult:
    """`already_confirmed_urls`/`resume_seed` (Story 2.17 AC 2/3, Story 2.16
    Task 3): resuming a paused/blocked run never re-explores a state already
    confirmed canonical — `already_confirmed_urls` seeds the BFS's
    `visited_pages` so those URLs are skipped entirely (not merely
    deduplicated at persist time, which Story 2.10 already does), and
    `resume_seed` seeds the initial `page_queue` with the frontier just past
    them, `(url, from_url)` pairs, instead of starting over at `base_url`.
    Both default to "nothing to resume from" — today's exact behaviour."""
    # Story 2.19: one loop-guard instance for the whole run — deferred
    # import for the same reason `_click_standalone_buttons` uses one (see
    # its own comment on the crawler/planner/state_identity import cycle).
    from discovery_worker import data_resolver, planner

    result = CrawlResult()
    sink = _CaptureSink(result, on_capture)
    loop_guard_state = planner.LoopGuardState()
    # Settings page's Max Discovery Duration — `None` means no wall-clock cap.
    deadline = time.monotonic() + max_duration_seconds if max_duration_seconds else None
    # Settings page's Interaction Level — orthogonal to `safety` (Story 2.12).
    interaction_level_gate = planner.InteractionLevelGate(interaction_level)
    # Story 2.13: one resolution log for the whole run, alongside the loop
    # guard — `data_resolver_pool` is loaded once by the caller (Story
    # 2.20's pool, seeded at Activity start) and passed straight through;
    # an empty dict here is exactly today's behaviour (pool consulted,
    # finds nothing, falls through to synthesis).
    resolution_log = data_resolver.ResolutionLog()
    page = await context.new_page()
    # Story 2.14 AC 2: installed once, before any app code runs, so every
    # `attachShadow` call this page ever makes (open or closed) is tracked.
    await page.add_init_script(_SHADOW_TRACKING_INIT_SCRIPT)
    reauth_attempts_since_last_page = 0
    # Story 2.9 AC 1a/2: attached once for this page's whole lifetime, next
    # to the existing "response" listener Story 2.2 uses for API capture —
    # not a second listener stack per readiness check.
    network_tracker = NetworkActivityTracker()
    network_tracker.attach(page)
    effective_page_load_timeout = page_load_timeout_seconds
    # Story 2.14 AC 5: queued by Playwright's own popup event, drained after
    # every click/submit that might have triggered one.
    popup_events: list = []
    # A bound built-in method (`popup_events.append`) can't hold the wrapper
    # attribute Playwright's handler-wrapping caches on the callable — must
    # be a plain function.
    page.on("popup", lambda popup: popup_events.append(popup))

    async def on_response(response: Response) -> None:
        request = response.request
        if request.resource_type in ("xhr", "fetch"):
            try:
                # Truncated, not parsed — this is signal for a later negative-
                # path Scenario prompt (Story 4.1), not a typed contract.
                body = (await response.text())[:500]
            except Exception:
                body = None
            await sink.add(
                CapturedApiCall(
                    page_url=_page_fingerprint(page.url),
                    method=request.method,
                    path=urlparse(request.url).path,
                    status_code=response.status,
                    response_summary=body,
                )
            )

    page.on("response", on_response)

    # `[ADDED 2026-07-23]` Seeding the very first page's `from_url` with the
    # login page (when one was captured pre-crawl by `establish_session`)
    # gives it its only edge into the rest of the navigation graph — without
    # this, `journey_clustering.py`'s connectivity-based grouping sees it as
    # an isolated island with nothing to form a "Sign in" journey's second
    # step from, and no candidate journey ever gets inferred for it.
    page_queue: list[tuple[str, str | None]] = (
        list(resume_seed) if resume_seed else [(_page_fingerprint(base_url), login_page_url)]
    )
    queued_urls: set[str] = {u for u, _ in page_queue}
    visited_pages: set[str] = set(already_confirmed_urls or ())
    visited_forms: set[str] = set()
    seen_form_signatures: set[tuple[str, str, tuple[tuple[str | None, str | None], ...]]] = set()
    # `[ADDED 2026-07-22]` A mid-page session expiry (see `_recover_login_if_needed`
    # and the reauth block below) re-processes the SAME page from scratch —
    # without this, a real short-lived-token app that expires *during* one
    # page's own button exploration (not just between pages) would restart
    # `_click_standalone_buttons`'s `seen_labels` empty every time, re-trying
    # already-clicked buttons before ever reaching new ones. Observed live: a
    # crawl stuck cycling the same 2 pages for 25+ minutes, never progressing,
    # because each retry re-did the same early candidates and expired again
    # before reaching new ones. Keyed by page fingerprint so unrelated pages
    # don't share state, persists across BFS re-queues of the same page.
    seen_button_labels_by_page: dict[str, set[str]] = {}

    def _maybe_enqueue(new_url: str | None, from_url: str) -> str:
        """Returns why a candidate URL was or wasn't queued — used both to
        actually drive the BFS and to power `_extract_and_enqueue_links`'s
        per-page skip-reason summary below (`[ADDED 2026-07-22]` — this used
        to be silent, which is exactly why a whole class of "page never
        gets crawled" bugs went unnoticed until a live run was manually
        compared against the real site's page list)."""
        if not new_url:
            return "empty"
        if not _same_origin(new_url, base_url):
            return "off-origin"
        if _is_self_referential_duplicate(new_url, base_url):
            return "malformed-duplicate-path"
        if _LOGOUT_RE.search(urlparse(new_url).path):
            # A plain `<a href="/logout">`-shaped link — same self-inflicted
            # session-ending risk as clicking a "Log out" button (see
            # `_LOGOUT_RE`'s definition above), just via ordinary link
            # scraping instead of a click.
            return "logout-link"
        if new_url in visited_pages:
            return "already-visited"
        if new_url in queued_urls:
            return "already-queued"
        page_queue.append((new_url, from_url))
        queued_urls.add(new_url)
        return "enqueued"

    async def _extract_and_enqueue_links(from_url: str) -> int:
        """Scrapes every `<a href>` currently in the DOM and enqueues each
        new same-origin destination. `[ADDED 2026-07-22]` Called not just
        once at page-load (the original behavior) but also after every
        button click / form submit that *doesn't* navigate — a dropdown,
        drawer, or accordion toggle very often renders its `<a>` items into
        the DOM for the first time on click (React/Angular conditional
        rendering) rather than just un-hiding a pre-rendered menu, so a
        single scrape right after `goto()` would never see them. This is
        what actually unlocks a nav menu's authenticated pages (Order
        History, Product Management, etc.) that only existed behind an
        "Account" dropdown.

        `[FIXED 2026-07-22]` A same-URL form submit/click can still trigger a
        real navigation (a self-redirect, or a reload back to the same
        route) even though the fingerprint-based `before_url == after_url`
        check upstream says nothing changed — the settle waits can resolve
        just before a second, in-flight navigation invalidates the page's
        JS execution context, and `eval_on_selector_all` then raises rather
        than returning. Observed live against shopbit.onwavemaker.com: this
        crashed straight out of `run_discovery_crawl` uncaught, failing the
        *entire* Discovery Run over one page's link-scrape timing, instead
        of just skipping that one scrape attempt like every other transient
        per-page failure in this file already does."""
        try:
            links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        except Exception as exc:
            logger.warning("  %s: link scrape failed, skipping (%s)", from_url, exc)
            return 0
        tally: dict[str, int] = {}
        new_links: list[str] = []
        for raw_link in links:
            reason = _maybe_enqueue(_page_fingerprint(raw_link), from_url)
            tally[reason] = tally.get(reason, 0) + 1
            if reason == "enqueued":
                new_links.append(_page_fingerprint(raw_link))
        logger.info(
            "  %s: %d <a href> found — %s",
            from_url,
            len(links),
            ", ".join(f"{count} {reason}" for reason, count in sorted(tally.items())) or "none",
        )
        if new_links:
            logger.info("  %s: newly discovered -> %s", from_url, new_links)
        return len(new_links)

    while page_queue:
        url, from_url = page_queue.pop(0)
        if url in visited_pages:
            continue
        visited_pages.add(url)
        queued_urls.discard(url)

        # Settings page's Max Pages / Max Discovery Duration — stop cleanly
        # and keep everything already captured in `result` (a `break`, not a
        # raise) rather than the exhaustive-traversal default below.
        if max_pages is not None and len(visited_pages) > max_pages:
            logger.info("discovery stopped early: max_pages (%d) reached", max_pages)
            break
        if deadline is not None and time.monotonic() >= deadline:
            logger.info("discovery stopped early: max_discovery_duration reached")
            break

        # Exhaustive traversal (Story 2.3) has no cap and a real site can
        # take far longer than any fixed timeout — heartbeating each
        # iteration lets Temporal tell "still working" apart from "worker
        # died," instead of a short start-to-close timeout killing (and
        # restarting from scratch) a crawl that's simply large.
        if heartbeat:
            heartbeat()

        # Story 2.18 AC 2/3: a small bounded retry before a 5xx/unreachable
        # destination becomes a `DiscoveryError` — a 4xx (e.g. a GET against
        # a POST-only route) is not a target-application *failure*, just not
        # a business page (Story 2.2 AC 9's existing skip, unchanged below),
        # so it's never retried and never logged as DISC-003.
        response = None
        nav_exc: Exception | None = None
        attempt = 0
        for attempt in range(_MAX_NAV_RETRIES + 1):
            if attempt and heartbeat:
                heartbeat()
            try:
                response = await page.goto(url, timeout=effective_page_load_timeout * 1000)
                nav_exc = None
            except Exception as exc:
                nav_exc = exc
                response = None
            if nav_exc is None and (response is None or response.status < 500):
                break
        if nav_exc is not None or (response is not None and response.status >= 500):
            reason = (
                f"{type(nav_exc).__name__}: {nav_exc}"
                if nav_exc
                else f"HTTP {response.status}"  # type: ignore[union-attr]
            )
            logger.warning(
                "skip %s: goto() failed after %d attempt(s) (%s)", url, attempt + 1, reason
            )
            if on_diagnostic:
                await _emit_diagnostic(
                    on_diagnostic,
                    "discovery_error",
                    {
                        "error_code": "DISC-003",
                        "message": (
                            f"{url} was unreachable after {attempt + 1} attempt(s) ({reason}). "
                            "Check whether the target application was under maintenance "
                            "during this run."
                        ),
                        "page_url": url,
                        "retry_count": attempt + 1,
                    },
                )
            continue
        if response is not None and response.status >= 400:
            # A 4xx destination (e.g. a GET against a POST-only route) is not
            # a business page — persisting it as one would hand the
            # Journey/Scenario model a broken page to build an assertion
            # against and land on. Marked visited above so it's never
            # retried; nothing about it (Page, links, forms, buttons) is
            # explored further.
            logger.warning("skip %s: HTTP %d", url, response.status)
            continue

        # `[ADDED 2026-07-22]` `goto()`'s default `waitUntil="load"` fires as
        # soon as the initial HTML/assets are done — many SPA frameworks
        # (React/Angular, which WaveMaker-generated apps are built on) then
        # make an additional async call (e.g. "fetch my permissions, then
        # render the nav") before the *authenticated* menu actually appears.
        # Scraping links immediately after `goto()`, with no settle wait at
        # all, could miss exactly that menu. Story 2.9's readiness gate
        # (network quiet + DOM stable + content present, bounded by
        # `page_load_timeout_seconds`) replaces the two ad-hoc waits this
        # used — `[FIXED 2026-07-22, again]`'s underlying observation (a
        # network-quiet signal alone resolves before an SPA's post-login
        # data fetch even starts) is exactly why AC 1 requires three signals,
        # not one.
        readiness = await wait_for_page_ready(
            page, effective_page_load_timeout, network_tracker, heartbeat, on_diagnostic
        )
        if on_diagnostic:
            await _emit_diagnostic(
                on_diagnostic,
                "page_readiness",
                {
                    "type": "page_settled" if readiness.settled else "page_not_settled",
                    "page_url": url,
                    "unsettled_signals": readiness.unsettled_signals,
                },
            )
        if heartbeat:
            heartbeat()

        try:
            screenshot = await page.screenshot()
            title = await page.title()
            # Synchronous S3 upload — off the event loop for the same
            # reason as the DB commit above (see `_CaptureSink.add`).
            key = await asyncio.to_thread(object_store.put, screenshot, discovery_run_id)
        except Exception as exc:
            # A screenshot/upload hiccup on one page previously failed the
            # *entire* run (any uncaught exception here escapes to
            # `discovery_activity`'s except-block, below) — treat it like
            # any other broken destination instead: skip the page, keep
            # crawling everything else.
            logger.warning("skip %s: screenshot/upload failed (%s)", url, exc)
            continue
        heading, structural_tokens = await _capture_state_signals(page)
        await sink.add(
            CapturedPage(
                url=page.url,
                title=title,
                object_storage_key=key,
                heading=heading,
                structural_tokens=structural_tokens,
            )
        )
        # Records how the crawler actually reached this page — without this,
        # plain link-followed BFS navigation (the vast majority of a normal
        # crawl) left `PageTransition` almost empty, since only click/form-
        # triggered navigation emitted one below.
        if from_url and from_url != url:
            await sink.add(CapturedTransition(from_url=from_url, to_url=url))

        # Story 2.4 (AD-11), checked before the exhaustive-traversal
        # continuation below: session expiry looks like an *unrequested*
        # redirect landing on a page with a password field — the crawler
        # asked to go to `url` but the server bounced it elsewhere. A page
        # reached normally (by clicking a real link, e.g. a "change
        # password" settings page) never redirects, so it can have a
        # password field without ever tripping this — password-field
        # presence alone is not sufficient, redirect-away-from-requested-url
        # is the actual signal (content-based rather than URL-list matching
        # so it also covers a single-URL app shell where the same route
        # serves both the login form and the authenticated view).
        was_redirected = _page_fingerprint(page.url) != url
        if was_redirected and await page.locator('input[type="password"]').count() > 0:
            # `[ADDED 2026-07-22]` A short-lived OAuth/OIDC access token
            # (observed live: a Keycloak-backed app) can expire well before
            # an exhaustive crawl finishes — treating this as unconditionally
            # terminal means such an app can *never* be fully discovered.
            # Replay the same login the crawl started with and resume this
            # exact page, bounded by `_MAX_CONSECUTIVE_REAUTH_ATTEMPTS` so a
            # genuinely broken login (wrong credential, an unhandled login
            # form) still terminates rather than retrying forever.
            if (
                auth_method == "standard_login"
                and credential is not None
                and reauth_attempts_since_last_page < _MAX_CONSECUTIVE_REAUTH_ATTEMPTS
            ):
                reauth_attempts_since_last_page += 1
                logger.warning(
                    "session expired mid-crawl: requested %s, redirected to %s — "
                    "attempting silent re-login (%d/%d)",
                    url,
                    page.url,
                    reauth_attempts_since_last_page,
                    _MAX_CONSECUTIVE_REAUTH_ATTEMPTS,
                )
                await attempt_login(page, credential, heartbeat=heartbeat)
                if heartbeat:
                    heartbeat()
                visited_pages.discard(url)
                queued_urls.add(url)
                page_queue.insert(0, (url, from_url))
                # Story 2.10 Task 7: this attempt's (partial) capture set is
                # done, even though the page itself is being re-queued — a
                # missed exit path here would strand it in the persist
                # layer's per-URL buffer forever.
                await sink.add(CapturedPageComplete(url=url))
                continue

            logger.warning(
                "session expired: requested %s, redirected to %s (password field present)",
                url,
                page.url,
            )
            if on_diagnostic:
                # Story 2.18 AC 3: DISC-002, logged the same way as every
                # other error code here — Story 2.4/AD-11 already owns the
                # actual detection/handling, this just gives it a matching
                # code.
                await _emit_diagnostic(
                    on_diagnostic,
                    "discovery_error",
                    {
                        "error_code": "DISC-002",
                        "message": (
                            f"Session expired mid-crawl: requested {url}, redirected to "
                            f"{page.url}. Re-authenticate to resume discovery."
                        ),
                        "page_url": url,
                        "retry_count": reauth_attempts_since_last_page,
                    },
                )
            await sink.add(CapturedPageComplete(url=url))
            await page.close()
            return CrawlResult(
                pages=result.pages,
                forms=result.forms,
                actions=result.actions,
                api_calls=result.api_calls,
                transitions=result.transitions,
                session_expired=True,
            )
        reauth_attempts_since_last_page = 0

        current_url = _page_fingerprint(page.url)
        await _extract_and_enqueue_links(current_url)

        # Story 2.9 AC 5/6: sample a repeating region (infinite scroll /
        # "Load More") before the generic loops below, and exclude the
        # matched control from them so it isn't also clicked as an ordinary
        # button.
        load_more_label = await _sample_scroll_or_pagination(
            page,
            current_url,
            heartbeat,
            on_diagnostic,
            network_tracker,
            effective_page_load_timeout,
        )
        if load_more_label:
            seen_button_labels_by_page.setdefault(current_url, set()).add(load_more_label)

        form_count = await page.locator("form").count()
        logger.info(
            "visiting %s (page %d/?, %d forms, queue=%d remaining)",
            url,
            len(visited_pages),
            form_count,
            len(page_queue),
        )
        for form_index in range(form_count):
            form_key = f"{_page_fingerprint(page.url)}#form-{form_index}"
            if form_key in visited_forms:
                continue
            visited_forms.add(form_key)
            try:
                new_url = await _fill_and_submit_form(
                    page,
                    f"form >> nth={form_index}",
                    _page_fingerprint(page.url),
                    sink,
                    seen_form_signatures,
                    rescan=_extract_and_enqueue_links,
                    heartbeat=heartbeat,
                    on_diagnostic=on_diagnostic,
                    popup_events=popup_events,
                    network_tracker=network_tracker,
                    timeout_seconds=effective_page_load_timeout,
                    data_resolver_pool=data_resolver_pool,
                    resolution_log=resolution_log,
                )
            except PlaywrightTimeoutError:
                # A form's DOM position can shift or vanish between the
                # `count()` above and this nth-index resolving (e.g. a
                # Statement page's lazy-loaded rows) — same class of bug
                # already fixed for buttons (see the "since-shifted index"
                # comment below). Skip this one form instead of letting a
                # raw Playwright timeout crash the whole discovery run.
                logger.warning(
                    "  %s: form #%d no longer resolves — skipping", current_url, form_index
                )
                if on_diagnostic:
                    await _emit_diagnostic(
                        on_diagnostic,
                        "discovery_error",
                        {
                            "error_code": "DISC-006",
                            "message": (
                                f"Form #{form_index} on {current_url} timed out resolving "
                                "(likely shifted/removed by page mutation) — skipped."
                            ),
                            "page_url": current_url,
                            "retry_count": 0,
                        },
                    )
                continue
            _maybe_enqueue(new_url, current_url)
            # `[FIXED 2026-08-05]` Compared against `url` — the raw queue
            # entry — instead of `current_url` (already computed above, at
            # the top of this iteration): whenever the *initial* navigation
            # to `url` itself lands somewhere else (a server-side redirect —
            # confirmed live: this app's bare origin 302s an authenticated
            # session straight to `/Dashboard`), `page.url` never equals `url`
            # even immediately after loading, with nothing to do with the form
            # submit at all. Every same-page form submit on such a page then
            # misfired this as "lost track", restored to the wrong (never-
            # actually-visited) `url` instead of the real `current_url`, and
            # DISC-005'd out of the rest of that page's forms.
            if _page_fingerprint(page.url) != current_url:
                await page.goto(current_url)
                if not await _recover_login_if_needed(page, current_url, credential, heartbeat):
                    logger.warning(
                        "  %s: session appears lost restoring after a form submit — "
                        "stopping form loop early",
                        current_url,
                    )
                    if on_diagnostic:
                        # Story 2.18 AC 3: DISC-005 — the browser lost track
                        # of the expected page/state after this form submit
                        # and restoring to it didn't work either.
                        await _emit_diagnostic(
                            on_diagnostic,
                            "discovery_error",
                            {
                                "error_code": "DISC-005",
                                "message": (
                                    f"Lost track of {current_url} after a form submit and "
                                    "could not restore to it — stopping this page's form "
                                    "loop early."
                                ),
                                "page_url": current_url,
                                "retry_count": 0,
                            },
                        )
                    break

        # Button-triggered navigation (e.g. an "Add to Cart" button that
        # isn't a plain <a href>) previously dead-ended here — the click was
        # captured as an Action/Transition but its destination was never
        # queued for further crawling, so any flow reachable only via such a
        # button was structurally invisible past the first click.
        for discovered_url in await _click_standalone_buttons(
            page,
            sink,
            base_url,
            rescan=_extract_and_enqueue_links,
            heartbeat=heartbeat,
            credential=credential,
            seen_labels=seen_button_labels_by_page.setdefault(current_url, set()),
            on_diagnostic=on_diagnostic,
            popup_events=popup_events,
            network_tracker=network_tracker,
            timeout_seconds=effective_page_load_timeout,
            entry_url=base_url,
            loop_guard_state=loop_guard_state,
            safety=safety,
            interaction_level=interaction_level_gate,
        ):
            _maybe_enqueue(discovered_url, current_url)

        # Story 2.14: tabs (AC 3), same-origin iframes (AC 1) and open shadow
        # roots (AC 2) — run after the page's own forms/buttons so widget
        # exploration sees the page in whatever state those left it.
        await _explore_tabs(page, sink, current_url, heartbeat, on_diagnostic)
        async for frame, depth in _iter_same_origin_frames(
            page.main_frame, 1, max_frame_depth, current_url, on_diagnostic
        ):
            await _capture_frame_widgets(
                frame,
                current_url,
                sink,
                seen_form_signatures,
                heartbeat,
                credential,
                on_diagnostic,
                depth,
                network_tracker=network_tracker,
                timeout_seconds=effective_page_load_timeout,
                loop_guard_state=loop_guard_state,
                data_resolver_pool=data_resolver_pool,
                resolution_log=resolution_log,
                safety=safety,
                interaction_level=interaction_level_gate,
            )
        shadow_widgets = await _collect_shadow_dom_widgets(page, current_url, on_diagnostic)
        if shadow_widgets:
            await _click_shadow_dom_buttons(
                page, sink, current_url, shadow_widgets, set(), heartbeat
            )

        # Story 2.10 Task 7: this page's full capture set (Page, every
        # Action/Form/ApiCall/Transition attributed to it) is now known —
        # the persist layer can classify SAME/VARIANT/NEW.
        await sink.add(CapturedPageComplete(url=current_url))

    logger.info(
        "crawl finished: %d pages, %d forms, %d actions, %d api calls, %d transitions",
        len(result.pages),
        len(result.forms),
        len(result.actions),
        len(result.api_calls),
        len(result.transitions),
    )
    await page.close()
    return result
