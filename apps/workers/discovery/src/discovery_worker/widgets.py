"""ARIA-first widget detection for tabs and dialogs/overlays (Story 2.14, AC
3-4). Frame and shadow-DOM traversal for capture stay in `crawler.py`
itself, next to the capture path they extend — see that story's Dev Notes
("a new file here would buy an import and nothing else"). This module is
the narrower classification/close-ladder logic `crawler.py` calls into.

React/Angular/Vue/Svelte/server-rendered markup all expose the same
accessibility surface when built to spec, which is why detection here reads
ARIA roles only, never a framework-specific DOM shape.
"""

from dataclasses import dataclass

from playwright.async_api import Locator, Page


@dataclass
class DialogCloseResult:
    closed: bool
    method: str  # "already_gone" | "escape" | "close_button" | "forced_navigation"


async def list_tabs(container: Page | Locator) -> list[Locator]:
    """Each `role="tab"` is a Tier-1 candidate action per AC 3."""
    return await container.locator('[role="tab"]').all()


async def detect_open_dialog(page: Page) -> Locator | None:
    """The ARIA-correct overlay signal (AC 4): `role="dialog"`/`"alertdialog"`
    or `aria-modal="true"`, currently visible. A bespoke overlay that skips
    ARIA entirely is the honest gap AC 7's low-confidence fallback exists
    for — this function does not guess beyond the accessibility tree."""
    locator = page.locator('[role="dialog"], [role="alertdialog"], [aria-modal="true"]')
    try:
        count = await locator.count()
    except Exception:
        return None
    for i in range(count):
        candidate = locator.nth(i)
        try:
            if await candidate.is_visible():
                return candidate
        except Exception:
            continue
    return None


async def close_dialog_ladder(
    page: Page,
    dialog: Locator,
    pre_dialog_url: str,
    heartbeat=None,
) -> DialogCloseResult:
    """Escape -> accessible Close/Cancel/X/Dismiss -> aria-label close ->
    forced navigation back to `pre_dialog_url`, verifying after every rung
    that the dialog is actually gone. This is the highest-risk piece of
    Story 2.14 (Dev Notes): an undetected/failed close leaves the crawl
    operating inside a modal for the rest of the run, so the forced-
    navigation fallback is mandatory, not best-effort."""

    async def _gone() -> bool:
        try:
            return not await dialog.is_visible()
        except Exception:
            return True

    if await _gone():
        return DialogCloseResult(True, "already_gone")

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    if heartbeat:
        heartbeat()
    if await _gone():
        return DialogCloseResult(True, "escape")

    for name in ("Close", "Cancel", "X", "Dismiss"):
        try:
            close_btn = dialog.get_by_role("button", name=name, exact=False)
            if await close_btn.count() > 0:
                await close_btn.first.click(timeout=1500)
                if heartbeat:
                    heartbeat()
                if await _gone():
                    return DialogCloseResult(True, "close_button")
        except Exception:
            continue

    try:
        close_by_label = dialog.locator('[aria-label="Close" i], [aria-label="Dismiss" i]')
        if await close_by_label.count() > 0:
            await close_by_label.first.click(timeout=1500)
            if heartbeat:
                heartbeat()
            if await _gone():
                return DialogCloseResult(True, "close_button")
    except Exception:
        pass

    try:
        await page.goto(pre_dialog_url)
    except Exception:
        return DialogCloseResult(False, "forced_navigation")
    if heartbeat:
        heartbeat()
    return DialogCloseResult(True, "forced_navigation")
