"""Stage 6 — breadth (PLAN.md §5, ways 4, 6, 7).

- Who can see what: sign in as each extra kind of user you added and try
  every screen Explorer knows; the result is an access chart.
- Pages nothing links to: read the app's own code (the files every browser
  downloads anyway) for page addresses, and visit the ones no menu leads to.
- Code-coverage radar: measure how much of the app's own code actually ran
  while visiting everything Explorer knows, and name the parts that never
  ran — places a person might still want to look.
"""

import re
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from explorer_core import ExplorerAccess, ExplorerRole, ExplorerRun
from playwright.async_api import Error as PlaywrightError
from sqlmodel import Session, select

from explorer_worker.browser import Eyes
from explorer_worker.db import engine
from explorer_worker.journal import Journal
from explorer_worker.mind import Mind
from explorer_worker.sense import url_pattern
from explorer_worker.session import Target, load_target, open_signed_in

MAX_SCREENS_PER_ROLE = 40
MAX_UNLINKED = 10
_BLOCKED = re.compile(
    r"(access denied|not authori[sz]ed|forbidden|no permission|don't have permission|"
    r"do not have permission|unauthori[sz]ed|\b401\b|\b403\b|not allowed)",
    re.IGNORECASE,
)
# Route-looking strings in front-end code: "#/Something", "/path/like/this",
# path: "x", pages: [...] — kept short and same-app.
_ROUTE_PATTERNS = [
    re.compile(r"""["'`]#/([A-Za-z][\w\-/]{1,60})["'`]"""),
    re.compile(r"""path\s*:\s*["'`](/?[A-Za-z][\w\-/:]{1,60})["'`]"""),
    re.compile(r"""["'`](/[a-z][a-z0-9\-]{2,40}(?:/[a-z][a-z0-9\-]{2,40}){0,2})["'`]"""),
]
_NOT_PAGES = re.compile(
    r"(\.(js|css|png|svg|json|ico|woff2?)$|/api/|/services/|/rest/|assets|static|node_modules)",
    re.IGNORECASE,
)


async def breadth(run_id: uuid.UUID, heartbeat: Callable[[], None]) -> None:
    journal = Journal(run_id)
    if journal.status() == "stopped":
        return
    target = load_target(run_id)
    journal.update_run(
        status="hunting", headline="Checking access, unlinked pages and code coverage"
    )
    insights: dict[str, Any] = {}
    eyes = await open_signed_in(target, journal)
    if eyes is not None:
        try:
            insights["unlinked"] = await _unlinked_pages(eyes, journal, target, heartbeat)
            insights["coverage"] = await _coverage_radar(eyes, journal, heartbeat)
        except PlaywrightError as exc:
            journal.event(
                "thought", "Couldn't finish the breadth checks", str(exc).splitlines()[0][:200]
            )
        finally:
            await eyes.close()
    insights["roles"] = await _roles_sweep(run_id, journal, target, heartbeat)
    journal.update_run(insights=insights)


# -- who can see what ----------------------------------------------------------


def _roles(target: Target) -> list[ExplorerRole]:
    with Session(engine) as session:
        return list(
            session.exec(
                select(ExplorerRole).where(ExplorerRole.application_id == target.application_id)
            ).all()
        )


async def _roles_sweep(
    run_id: uuid.UUID, journal: Journal, target: Target, heartbeat: Callable[[], None]
) -> list[dict[str, Any]]:
    roles = _roles(target)
    if not roles:
        return []
    screens = [s for s in journal.screen_rows() if not s.condition][:MAX_SCREENS_PER_ROLE]
    summary: list[dict[str, Any]] = []
    for role in roles:
        heartbeat()
        journal.event(
            "phase",
            f"Exploring as: {role.name}",
            "Trying every known screen with this kind of user's login.",
        )
        as_role = Target(**{**vars(target), "secret_ref": role.secret_ref, "notes": target.notes})
        eyes = await open_signed_in(as_role, journal)
        if eyes is None:
            summary.append({"role": role.name, "signed_in": False})
            continue
        allowed = blocked = 0
        try:
            for screen in screens:
                heartbeat()
                ok, note = await _can_open(eyes, screen.url)
                allowed += ok
                blocked += not ok
                with Session(engine) as session:
                    session.add(
                        ExplorerAccess(
                            run_id=run_id,
                            role=role.name,
                            screen_id=screen.id,
                            allowed=ok,
                            note=note,
                        )
                    )
                    session.commit()
        finally:
            await eyes.close()
        summary.append(
            {"role": role.name, "signed_in": True, "allowed": allowed, "blocked": blocked}
        )
        journal.event(
            "summary",
            f"{role.name}: can open {allowed} of {allowed + blocked} screens",
            "See who can see what on the Report.",
        )
    return summary


async def _can_open(eyes: Eyes, url: str) -> tuple[bool, str | None]:
    assert eyes.page is not None
    status, _ = await eyes.goto(url)
    if status in (401, 403):
        return False, f"The app answered {status}"
    try:
        if await eyes.page.locator("input[type=password]").first.is_visible():
            return False, "Sent to the sign-in page"
        text = await eyes.page.evaluate(
            "() => document.body ? document.body.innerText.slice(0, 3000) : ''"
        )
    except PlaywrightError:
        return False, "Screen could not be opened"
    if _BLOCKED.search(text):
        return False, "The app says this user isn't allowed"
    if url_pattern(eyes.page.url) != url_pattern(url) and url_pattern(eyes.page.url) == url_pattern(
        eyes.origin + "/"
    ):
        return False, "Sent back to the home screen"
    return True, None


# -- pages nothing links to -----------------------------------------------------


def routes_in_code(code: str) -> set[str]:
    found: set[str] = set()
    for pattern in _ROUTE_PATTERNS:
        for match in pattern.findall(code):
            route = match if isinstance(match, str) else match[0]
            if not _NOT_PAGES.search(route) and ":" not in route:
                found.add(route)
    return found


async def _unlinked_pages(
    eyes: Eyes, journal: Journal, target: Target, heartbeat: Callable[[], None]
) -> list[str]:
    page = eyes.page
    assert page is not None
    await eyes.goto(target.app_url)
    origin = eyes.origin
    scripts = await page.evaluate("() => [...document.scripts].map(s => s.src).filter(Boolean)")
    scripts = [s for s in scripts if s.startswith(origin)][:15]
    cookies = {c.get("name", ""): c.get("value", "") for c in await page.context.cookies()}
    routes: set[str] = set()
    async with httpx.AsyncClient(timeout=30, cookies=cookies, verify=False) as client:
        for src in scripts:
            try:
                routes |= routes_in_code((await client.get(src)).text)
            except httpx.HTTPError:
                continue
    hash_routing = "#/" in target.app_url or "#/" in page.url
    base = target.app_url.split("#")[0]
    known = {s.url_pattern for s in journal.screen_rows()}
    candidates = []
    for route in sorted(routes):
        url = (
            f"{base.rstrip('/')}/#/{route.lstrip('#/')}"
            if hash_routing or not route.startswith("/")
            else urljoin(origin, route)
        )
        if urlsplit(url).netloc == urlsplit(origin).netloc and url_pattern(url) not in known:
            candidates.append(url)
    journal.event(
        "phase",
        "Reading the app's own code for hidden pages",
        f"Found {len(routes)} page addresses in the code; {len(candidates)} aren't on the map yet.",
    )
    mind = Mind(
        journal,
        target.notes,
        heartbeat,
        condition="it's opened directly — nothing in the app links to it",
        home_url=target.app_url,
    )
    visited: list[str] = []
    for url in candidates[:MAX_UNLINKED]:
        heartbeat()
        status, load_ms = await eyes.goto(url)
        if status and status >= 400:
            continue
        visit = await eyes.look(url, status, load_ms)
        body = (
            " ".join(visit.inventory.get("headings") or [])
            + (visit.inventory.get("body_text") or "")[:300]
        )
        landed = url_pattern(page.url)
        if len(body.strip()) < 30 or landed in known:
            continue  # blank, or the app redirected somewhere already known
        await mind.take_in(visit, "Found in the app's code", action="Open directly")
        visited.append(url)
    return visited


# -- code-coverage radar --------------------------------------------------------


async def _coverage_radar(
    eyes: Eyes, journal: Journal, heartbeat: Callable[[], None]
) -> dict[str, Any]:
    page = eyes.page
    assert page is not None
    cdp = await page.context.new_cdp_session(page)
    await cdp.send("Profiler.enable")
    await cdp.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": False})
    for screen in [s for s in journal.screen_rows() if not s.condition][:40]:
        heartbeat()
        try:
            await eyes.goto(screen.url)
        except PlaywrightError:
            continue
    result = await cdp.send("Profiler.takePreciseCoverage")
    await cdp.send("Profiler.stopPreciseCoverage")
    report = coverage_summary(result.get("result", []), eyes.origin)
    if report["functions"]:
        journal.event(
            "summary",
            f"Code coverage: {report['percent']}% of the app's code ran",
            (
                "Parts of the code that never ran while visiting everything I know: "
                + ", ".join(report["never_ran"][:12])
            )
            if report["never_ran"]
            else "Nearly everything I can reach has been exercised.",
        )
    return report


_BUSINESS_WORD = re.compile(
    r"(approve|reject|submit|cancel|delete|refund|export|import|upload|renew|escalat|assign|transfer|"
    r"invoice|payment|pay|claim|policy|quote|order|report|review|archive|restore|reset|notify|schedule)",
    re.IGNORECASE,
)


# Third-party code shipped with the app (grids, frameworks, polyfills) isn't
# the app's own behaviour — leave it out of the radar.
_LIBRARY = re.compile(
    r"(vendor|polyfill|runtime|node_modules|chunk-vendors|/lib/|/libs/|revogr|ag-grid|angular|"
    r"react-dom|jquery|bootstrap|moment|lodash|wm-libs|wavemaker\.app)",
    re.IGNORECASE,
)


def coverage_summary(scripts: list[dict[str, Any]], origin: str) -> dict[str, Any]:
    """Share of the app's own functions that ran, and business-sounding ones
    that never did (pure — tests/test_breadth.py)."""
    total = ran = 0
    never: list[str] = []
    for script in scripts:
        url = str(script.get("url", ""))
        if not url.startswith(origin) or _LIBRARY.search(url):
            continue
        for fn in script.get("functions", []):
            name = fn.get("functionName") or ""
            if not name:
                continue
            total += 1
            executed = any(r.get("count", 0) > 0 for r in fn.get("ranges", []))
            ran += executed
            looks_own = "." not in name and not name.startswith(("define", "_")) and len(name) > 4
            if not executed and looks_own and _BUSINESS_WORD.search(name) and name not in never:
                never.append(name)
    return {
        "functions": total,
        "ran": ran,
        "percent": round(100 * ran / total) if total else 0,
        "never_ran": never[:30],
    }


def run_insights(run_id: uuid.UUID) -> dict[str, Any]:
    with Session(engine) as session:
        run = session.get(ExplorerRun, run_id)
        return dict(run.insights) if run else {}
