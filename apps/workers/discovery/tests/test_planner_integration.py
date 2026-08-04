"""Story 2.11 Task 7: the State Return ladder wired into the real crawl —
real Chromium against `fixtures/target_app.py`, same convention as
test_crawler.py.
"""

import json
import uuid

import pytest
from discovery_worker.crawler import CapturedAction, run_discovery_crawl
from discovery_worker.session import establish_session
from playwright.async_api import async_playwright


class FakeObjectStore:
    def put(self, data: bytes, discovery_run_id: uuid.UUID) -> str:
        return "fake/0"


async def _crawl_route(target_app_url: str, route: str):
    credential = json.dumps({"username": "qa", "password": "qa-pass"}).encode()
    captured: list = []
    diagnostics: list[tuple[str, dict]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await establish_session(
            browser, auth_method="standard_login", credential=credential, base_url=target_app_url
        )
        await run_discovery_crawl(
            context,
            f"{target_app_url}{route}",
            FakeObjectStore(),
            uuid.uuid4(),
            auth_method="standard_login",
            credential=credential,
            on_capture=captured.append,
            on_diagnostic=lambda kind, payload: diagnostics.append((kind, payload)),
        )
        await context.close()
        await browser.close()
    return captured, diagnostics


@pytest.mark.asyncio
async def test_ladder_exhausts_and_records_unreached_when_no_rung_reconstructs_the_state(
    target_app_url: str,
) -> None:
    """AC 6: a state whose content changes on every re-visit (simulating a
    server-side wizard with no deep link) exhausts all four confirmable
    rungs and gives up honestly — not an infinite retry, not a silent
    drop."""
    captured, diagnostics = await _crawl_route(target_app_url, "stuck")

    unreached = [
        payload
        for kind, payload in diagnostics
        if kind == "unreached" and payload.get("reason") == "return_failed"
    ]
    assert unreached, diagnostics
    assert unreached[0]["last_rung_attempted"] == "gave_up"
    assert unreached[0]["attempts_used"] > 0

    # The "Leave" button that triggered the give-up is still captured as an
    # Action — only candidates *after* it in the group are unreached, per
    # AC 4 ("EXECUTE performs the action").
    actions = [item for item in captured if isinstance(item, CapturedAction)]
    assert any(a.description == "Leave" for a in actions)
    # "Second button" comes after "Leave" in DOM order and is never reached
    # once the ladder gives up on restoring /stuck.
    assert not any(a.description == "Second button" for a in actions)


@pytest.mark.asyncio
async def test_ladder_succeeds_via_browser_back_on_a_real_recoverable_navigation(
    target_app_url: str,
) -> None:
    """The common case: a link-out-and-back reconstructs the original page
    via rung 2/3, and every subsequent Tier-1 candidate on that page is
    still tried afterward — this is the existing "left-nav sidebar" shape
    `crawler.py` was already built to handle, now going through the formal
    ladder instead of the old single-attempt restore."""
    captured, diagnostics = await _crawl_route(target_app_url, "about")

    succeeded = [
        payload
        for kind, payload in diagnostics
        if kind == "state_return" and payload["rung"] in ("browser_back", "renavigate")
    ]
    assert succeeded, diagnostics

    actions = [item for item in captured if isinstance(item, CapturedAction)]
    # /about's shared left-nav has both "Dashboard" (navigates away) and
    # "Widgets" (also navigates away) — both must be reachable, proving the
    # ladder restored the state between them rather than stranding the run
    # after the first navigating click.
    assert any(a.description == "Dashboard" for a in actions)
    assert any(a.description == "Widgets" for a in actions)
