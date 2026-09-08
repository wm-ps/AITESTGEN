"""Targeted live Playwright inspection for the self-heal loop
(`HealTestActivity`, `activities.py`) — the first in-process (not
subprocess) Playwright use in this worker. Everything else here shells out
to `npx playwright test` and parses its JSON report; this module exists
because diagnosing a stale/invalid locator needs the AI to see the
*current* page, not another run of the already-broken test.

Deliberately narrow: one scoped, single-page browser session per call,
reusing the TestRun's own existing auth state (never re-authenticates,
never crawls), bounded by its own timeout independent of
`HealTestActivity`'s overall Temporal activity timeout, best-effort (never
raises — a failed/timed-out inspection just means the AI proceeds without
it, exactly like a failed screenshot fetch already does).
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from ai_provider.hosted import _describe_live_locators
from locator_capture import extract_page_locator_snapshot
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Navigation + extraction budget for one inspection call. Small relative to
# HealTestActivity's own activity timeout — this only ever runs once per
# heal attempt (never once per loop iteration beyond that), so the worst
# case across DiscoverySettings.max_heal_attempts stays a small fraction of
# the overall budget.
LIVE_INSPECTION_TIMEOUT_SECONDS = 45
_NAVIGATION_TIMEOUT_MS = 20_000


@dataclass
class LiveInspectionResult:
    # The *resolved* page.url() after navigation settles — not simply an
    # echo of the requested target_url. They can legitimately differ (a
    # redirect to a login/error page, or the target itself being the wrong
    # page for this failure), and that difference is exactly what the log
    # evidence below exists to surface.
    url: str
    locator_candidates: list[dict]
    page_title: str | None
    # Main frame + any child frames' (url, name) — best-effort log context;
    # empty for a single-frame page (the common case).
    frames: list[dict] = field(default_factory=list)
    # Playwright's own `[ref=eN]`-annotated accessibility tree
    # (`Locator.aria_snapshot(mode="ai")`, verified directly — "ai" mode is
    # what actually adds the `[ref=...]` markers; "default" mode omits
    # them) — real Playwright output, never touched by the LLM. `None` only
    # if the page itself couldn't be snapshotted at all.
    aria_snapshot: str | None = None


def _live_inspection_enabled() -> bool:
    # Operational kill switch, not a per-tenant product setting — the
    # deterministic trigger (_is_locator_failure) plus this function's own
    # timeout are already the cost/safety gate; this exists only so an
    # operator can turn the capability off entirely if it misbehaves in
    # production, without a Settings/migration/UI change.
    return os.environ.get("EXECUTION_WORKER_LIVE_INSPECTION_ENABLED", "true").lower() not in (
        "0",
        "false",
        "no",
    )


async def _run_live_inspection(
    *, target_url: str, auth_state_path: Path | None
) -> LiveInspectionResult | None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await (
                browser.new_context(storage_state=str(auth_state_path))
                if auth_state_path is not None
                else browser.new_context()
            )
            try:
                page = await context.new_page()
                await page.goto(
                    target_url, wait_until="domcontentloaded", timeout=_NAVIGATION_TIMEOUT_MS
                )
                candidates = await extract_page_locator_snapshot(page)
                title = await page.title()
                # Best-effort: frame enumeration and the aria snapshot are
                # log context, never load-bearing — either failing just
                # means that piece of evidence is unavailable, same
                # tolerance as this whole function's own outer best-effort.
                try:
                    frames = [{"url": f.url, "name": f.name} for f in page.frames]
                except Exception:  # noqa: BLE001 — see module docstring's tolerance
                    frames = []
                try:
                    aria_snapshot = await page.locator("html").aria_snapshot(mode="ai")
                except Exception:  # noqa: BLE001 — see module docstring's tolerance
                    aria_snapshot = None
                return LiveInspectionResult(
                    url=page.url,
                    locator_candidates=candidates,
                    page_title=title,
                    frames=frames,
                    aria_snapshot=aria_snapshot,
                )
            finally:
                await context.close()
        finally:
            await browser.close()


async def run_live_inspection(
    *,
    project_dir: Path,
    target_url: str,
    timeout_seconds: int = LIVE_INSPECTION_TIMEOUT_SECONDS,
) -> LiveInspectionResult | None:
    """Launch a scoped, single-page Chromium context reusing this TestRun's
    own auth session (`project_dir/.auth/state.json`, the same file the
    assembled project's `authenticated` Playwright project already points
    `storageState` at — never a fresh login), navigate to `target_url`,
    extract a bounded locator snapshot for that one page, then close
    everything. Best-effort: returns `None` on any failure or timeout
    instead of raising, so a bad inspection never blocks or fails the heal
    attempt it was meant to help — same tolerance as
    `_fetch_latest_screenshot_sync` in `activities.py`."""
    auth_state_path = project_dir / ".auth" / "state.json"
    logger.info("HealTestActivity: live inspection starting: requested_url=%s", target_url)
    try:
        result = await asyncio.wait_for(
            _run_live_inspection(
                target_url=target_url,
                auth_state_path=auth_state_path if auth_state_path.exists() else None,
            ),
            timeout=timeout_seconds,
        )
    except Exception:
        logger.warning(
            "HealTestActivity: live inspection of %s failed or timed out, "
            "continuing without it",
            target_url,
            exc_info=True,
        )
        return None
    if result is None:
        return None

    # Every field logged below comes from `result` (this call's own
    # LiveInspectionResult) or the `target_url` parameter above — never
    # Discovery's cached known_pages/known_locators, which this function
    # has no access to at all (it only ever takes project_dir/target_url).
    logger.info(
        "HealTestActivity: live inspection landed: requested_url=%s resolved_url=%s match=%s",
        target_url,
        result.url,
        result.url == target_url,
    )
    logger.info(
        "HealTestActivity: live inspection page_title=%r, %d frame(s)",
        result.page_title,
        len(result.frames),
    )
    logger.info(
        "HealTestActivity: live inspection observed %d locator candidate(s) on the live page:\n%s",
        len(result.locator_candidates),
        _describe_live_locators(result.locator_candidates),
    )
    if result.aria_snapshot:
        logger.info(
            "HealTestActivity: live inspection captured real Playwright "
            "aria_snapshot(mode='ai') for the live page:\n%s",
            result.aria_snapshot,
        )
    else:
        logger.info(
            "HealTestActivity: live inspection aria_snapshot unavailable for this page"
        )
    return result
