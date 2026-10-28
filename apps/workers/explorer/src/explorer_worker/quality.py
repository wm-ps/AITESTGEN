"""Page-quality checks: broken images (23), console errors and failed
requests (25, 39), phone-width layout (35/36) and labelled fields (37).

These are measured by the browser itself, not judged by the model, so the
same check runs the same way in Explorer and in the exported test. Each one
is planned per real screen and proven like any scenario: it must give the
same result every time; a check that fails every time is a bug found."""

import json
from typing import Any
from urllib.parse import urlsplit

from explorer_worker.browser import Eyes

PHONE = {"width": 390, "height": 844}

# name -> (title, expected)
CHECKS: dict[str, tuple[str, str]] = {
    "loads_cleanly": (
        "{screen} loads without script errors or failed requests",
        "Opening the screen shows no script errors and every request to the app succeeds.",
    ),
    "no_broken_images": (
        "{screen} has no broken images",
        "Every picture and icon on the screen loads.",
    ),
    "fits_phone": (
        "{screen} fits a phone screen without sideways scrolling",
        "At phone width (390 px) the screen needs no sideways scrolling.",
    ),
    "fields_labelled": (
        "Every field on {screen} has a label",
        "Every field says what it is for, so screen readers and the browser can name it.",
    ),
}

# Browser-side measurements: each returns a list of problems (empty = fine),
# or null when there is nothing on the screen to check.
_JS = {
    "no_broken_images": """() => {
  const shown = [...document.images].filter((i) => i.offsetParent);
  if (!shown.length) return null;
  return shown.filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.currentSrc || i.src).slice(0, 10);
}""",
    "fits_phone": """() => {
  const extra = document.documentElement.scrollWidth - window.innerWidth;
  return extra > 1 ? [`${extra}px wider than the screen`] : [];
}""",
    "fields_labelled": """() => {
  const fields = [...document.querySelectorAll('input, select, textarea')].filter((f) =>
    f.offsetParent && !['hidden', 'submit', 'button', 'reset', 'image'].includes((f.type || '').toLowerCase()));
  if (!fields.length) return null;
  const named = (f) => (f.labels && f.labels.length) || f.getAttribute('aria-label') || f.getAttribute('aria-labelledby') || f.getAttribute('title');
  return fields.filter((f) => !named(f)).map((f) => f.name || f.id || f.tagName.toLowerCase()).slice(0, 10);
}""",
}


# Kept so older runs' phone checks still prove and export, but no longer
# planned: responsive scenarios aren't wanted for now.
NOT_PLANNED = {"fits_phone"}


def planned_checks(screen: dict[str, Any]) -> list[str]:
    """The checks worth planning for a screen (labels only where it has fields)."""
    return [
        name
        for name in CHECKS
        if name not in NOT_PLANNED and (name != "fields_labelled" or screen.get("fields"))
    ]


def test_row(name: str, screen: dict[str, Any]) -> dict[str, Any]:
    title, expected = CHECKS[name]
    return {
        "kind": "page_quality",
        "title": title.format(screen=screen["name"]),
        "purpose": "Checked by the browser itself on every run.",
        "start_screen": screen["name"],
        "steps": [f"Open {screen['name']}", "Check: " + expected],
        "expected": expected,
        "check": {"kind": "page_quality", "value": name},
    }


async def measure(eyes: Eyes, name: str, url: str) -> list[str] | None:
    """Open `url` fresh and run check `name`: the problems found, [] when
    fine, None when the screen has nothing to check."""
    page = eyes.page
    assert page is not None
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    problems: list[str] = []

    def on_console(message: Any) -> None:
        if message.type == "error":
            problems.append(f"Script error: {message.text[:200]}")

    def on_page_error(error: Any) -> None:
        problems.append(f"Script crashed: {str(error)[:200]}")

    def on_response(response: Any) -> None:
        if response.url.startswith(origin) and response.status >= 400:
            problems.append(f"{response.status} {response.url[:200]}")

    def on_failed(request: Any) -> None:
        if request.url.startswith(origin):
            problems.append(f"Request failed: {request.url[:200]}")

    listeners = {
        "console": on_console,
        "pageerror": on_page_error,
        "response": on_response,
        "requestfailed": on_failed,
    }
    await page.set_viewport_size(PHONE if name == "fits_phone" else {"width": 1440, "height": 900})
    await page.goto("about:blank")
    if name == "loads_cleanly":
        for event, handler in listeners.items():
            page.on(event, handler)
    try:
        await eyes.goto(url)
        if name == "loads_cleanly":
            return sorted(set(problems))
        return await page.evaluate(_JS[name])
    finally:
        if name == "loads_cleanly":
            for event, handler in listeners.items():
                page.remove_listener(event, handler)


def playwright_code(title: str, name: str, url: str, tag: str | None, failing: str | None) -> str:
    """The exported test: the same measurement, as a Playwright assertion."""
    q = json.dumps
    lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        "const NAVIGATION_TIMEOUT_MS = 30000;",
        "",
        f"test({q(title)}{f', {{ tag: {q(tag)} }}' if tag else ''}, async ({{ page }}) => {{",
    ]
    if failing:
        # A known bug: parked like Explorer's other known-bug tests.
        lines.append(f"  test.fixme(true, {q('Known bug — the app currently: ' + failing)});")
    if name == "fits_phone":
        lines.append(f"  await page.setViewportSize({q(PHONE)});")
    if name == "loads_cleanly":
        origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
        lines += [
            "  const problems: string[] = [];",
            f"  const origin = {q(origin)};",
            "  page.on('console', (m) => { if (m.type() === 'error') problems.push(`Script error: ${m.text()}`); });",
            "  page.on('pageerror', (e) => problems.push(`Script crashed: ${e.message}`));",
            "  page.on('response', (r) => { if (r.url().startsWith(origin) && r.status() >= 400) problems.push(`${r.status()} ${r.url()}`); });",
            "  page.on('requestfailed', (r) => { if (r.url().startsWith(origin)) problems.push(`Request failed: ${r.url()}`); });",
        ]
    lines += [
        f"  await page.goto({q(url)}, {{ timeout: NAVIGATION_TIMEOUT_MS }});",
        "  await page.waitForLoadState('networkidle', { timeout: NAVIGATION_TIMEOUT_MS }).catch(() => {});",
    ]
    if name == "loads_cleanly":
        lines.append("  expect(problems).toEqual([]);")
    else:
        lines.append(f"  expect(await page.evaluate({q(_JS[name])}) ?? []).toEqual([]);")
    lines.append("});")
    return "\n".join(lines) + "\n"
