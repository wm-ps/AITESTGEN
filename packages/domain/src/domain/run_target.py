"""Which browsers and which window size a TestRun executes against.

A run has one window size and a list of browsers; every TestResult in the run
is one (test x browser). The size lives on the run, not on each result,
because it is the same for all of them.

The defaults are exactly what execution did before this existed (Playwright's
`Desktop Chrome` preset: bundled Chromium at 1280x720), so every earlier run
and schedule reads correctly with no backfill.

The labels the UI shows (Chrome / Firefox / Safari) are the browser *engines*
Playwright bundles — Safari is the WebKit engine, not macOS Safari.
"""

from typing import Literal

Browser = Literal["chromium", "firefox", "webkit"]

BROWSERS: tuple[Browser, ...] = ("chromium", "firefox", "webkit")
DEFAULT_BROWSER: Browser = "chromium"

# What users see for each engine. Safari is the WebKit engine, not macOS Safari.
BROWSER_LABELS: dict[str, str] = {"chromium": "Chrome", "firefox": "Firefox", "webkit": "Safari"}

# Healing is only done for this browser (see HealTestActivity): a heal rewrites
# the one test every browser shares, so healing on another browser would hide a
# real browser difference instead of fixing a stale locator.
HEAL_BROWSER: Browser = "chromium"

DEFAULT_VIEWPORT_WIDTH = 1280
DEFAULT_VIEWPORT_HEIGHT = 720

# Desktop windows only. Bounds, not a preset list, so a custom size is allowed.
MIN_VIEWPORT_WIDTH, MAX_VIEWPORT_WIDTH = 800, 3840
MIN_VIEWPORT_HEIGHT, MAX_VIEWPORT_HEIGHT = 500, 2160


def normalize_browsers(browsers: list[str] | None) -> list[str]:
    """The browsers a run will use, reference browser first, then the rest in
    the order given. `None` means the default. Raises `ValueError` for an
    empty list, a duplicate or an unknown browser — callers surface that as a
    400, so the message is user-readable."""
    if browsers is None:
        return [DEFAULT_BROWSER]
    if not browsers:
        raise ValueError("Select at least one browser.")
    unknown = [b for b in browsers if b not in BROWSERS]
    if unknown:
        raise ValueError(f"Unknown browser: {unknown[0]}.")
    if len(set(browsers)) != len(browsers):
        raise ValueError("Each browser can only be selected once.")
    # Reference browser first so its heal lands before the others run the test.
    return sorted(browsers, key=lambda b: (b != HEAL_BROWSER, browsers.index(b)))


def validate_viewport(width: int | None, height: int | None) -> tuple[int, int]:
    """The (width, height) a run will use. Both missing means the default;
    one without the other, or a size out of bounds, raises `ValueError`."""
    if width is None and height is None:
        return DEFAULT_VIEWPORT_WIDTH, DEFAULT_VIEWPORT_HEIGHT
    if width is None or height is None:
        raise ValueError("Enter both a width and a height.")
    if not MIN_VIEWPORT_WIDTH <= width <= MAX_VIEWPORT_WIDTH:
        raise ValueError(
            f"Width must be between {MIN_VIEWPORT_WIDTH} and {MAX_VIEWPORT_WIDTH}."
        )
    if not MIN_VIEWPORT_HEIGHT <= height <= MAX_VIEWPORT_HEIGHT:
        raise ValueError(
            f"Height must be between {MIN_VIEWPORT_HEIGHT} and {MAX_VIEWPORT_HEIGHT}."
        )
    return width, height
