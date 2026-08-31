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
from dataclasses import dataclass
from pathlib import Path

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
    url: str
    locator_candidates: list[dict]
    page_title: str | None


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
                return LiveInspectionResult(
                    url=target_url, locator_candidates=candidates, page_title=title
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
    try:
        return await asyncio.wait_for(
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
