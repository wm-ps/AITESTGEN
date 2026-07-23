"""A tiny locally-hosted test target for DiscoveryActivity's crawl loop.

Not part of the shipped product — a test fixture only, standing in for "a
locally-hosted test target" (Stories 2.2/2.3/2.4's own verification
language). Session-cookie auth, a couple of linked pages, one form, one
fetch-triggered API call — enough to exercise every Evidence type Story 2.2
needs to prove (page/action/form/api_call/state_transition), plus a
deterministic, request-counted session-expiry trigger for Story 2.4.
"""

import uuid

from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

_valid_sessions: set[str] = set()
_items: list[str] = ["Sample item", "Second item"]
_request_count = 0
_expire_after: int | None = None
_recoverable_expiry = False
_already_expired_once = False


def configure(expire_after: int | None, recoverable_expiry: bool = False) -> None:
    """Test-only: force session expiry after N authenticated requests. Also
    resets `_items`/`_valid_sessions` — this module is imported once and
    shared across the whole pytest session (a fresh uvicorn server per test
    still closes over the same globals), so without this reset, an earlier
    test's "Add item" submissions would silently leak into a later test's
    request-count-sensitive assertions.

    `recoverable_expiry` (`[ADDED 2026-07-22]`): the default, permanent
    ratchet (every request past the threshold keeps invalidating) models
    Story 2.4's original "terminal" expiry. Set `True` to model a real
    short-lived-OAuth-token app instead — the session invalidates *once*,
    then a fresh login (the crawler's own mid-crawl re-auth) stays valid for
    the rest of the crawl, proving recovery actually resumes traversal
    rather than just retrying forever."""
    global _expire_after, _request_count, _items, _valid_sessions, _recoverable_expiry, _already_expired_once
    _expire_after = expire_after
    _recoverable_expiry = recoverable_expiry
    _already_expired_once = False
    _request_count = 0
    _items = ["Sample item", "Second item"]
    _valid_sessions = set()


def _authenticated(request: Request) -> bool:
    global _request_count, _already_expired_once
    token = request.cookies.get("session")
    if token not in _valid_sessions:
        return False
    _request_count += 1
    if (
        _expire_after is not None
        and _request_count > _expire_after
        and not (_recoverable_expiry and _already_expired_once)
    ):
        _valid_sessions.discard(token)
        if _recoverable_expiry:
            _already_expired_once = True
        return False
    return True


# A shared header on every authenticated page, reproducing a real
# false-loop report: a nameless-input, action="#" form (e.g. a quick-search
# icon). Method defaults to GET (as real search boxes are), and the input
# has no `name` so the browser's submission carries no query string at all —
# it just re-requests the current page with a "#" fragment appended. The
# crawler must not treat that as a new page.
_HEADER = """<form action="#"><input type="text"></form>"""

# A persistent left-nav sidebar shown on /about, /settings, /cart, and
# /order-history (deliberately *not* on the dashboard itself) — reproduces a
# real observed shape (a Next.js back-office app): every route shares the
# same nav, and "Dashboard" (pointing back to a page already visited) sits
# before "Widgets" in DOM order. The crawler must restore the page after
# "Dashboard" navigates away and keep going to reach "Widgets" — the old
# stop-entirely-on-navigation behavior would reach "Widgets" from the
# dashboard's own visit only by coincidence and never from any other page.
_APP_NAV = """
<nav>
  <button onclick="window.location='/'">Dashboard</button>
  <button onclick="window.location='/widgets'">Widgets</button>
</nav>
"""


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> str:
    if not _authenticated(request):
        # Reproduces a real observed shape (shopbit.onwavemaker.com): the
        # landing page is public marketing content with no password field at
        # all — the login form lives behind a separate, *icon-only* link (no
        # visible text, no aria-label — just `<span class="icon-person">`),
        # not inline here. `establish_session` must follow it by `href`, not
        # by matching link text that doesn't exist.
        return """
        <html><body>
        <a href="/login"><span style="display:inline-block;width:16px;height:16px">&#9679;</span></a>
        </body></html>
        """
    return f"""
    <html><body>
    <nav>
      <button id="nav-menu">Menu</button>
      <a href="#" id="account-menu" onclick="revealAccountMenu(); return false;">Account</a>
      <div id="account-dropdown"></div>
    </nav>
    <script>
      // Reproduces a Bootstrap-style dropdown toggle built as an `<a>`, not a
      // `<button>` — and one whose menu items are injected into the DOM only
      // on click (React/Angular conditional rendering), not merely
      // CSS-unhidden. The crawler must click this `<a>` (dead href, no real
      // navigation target) to ever discover "Order History" behind it.
      function revealAccountMenu() {{
        document.getElementById('account-dropdown').innerHTML =
          '<a href="/order-history">Order History</a> <a href="/logout">Log out</a>';
      }}
    </script>
    {_HEADER}
    <h1>Dashboard</h1>
    <a href="/items">Items</a>
    <a href="/about">About</a>
    <a href="/settings">Settings</a>
    <form id="newsletter" onsubmit="return false;">
      <input type="email" name="newsletter_email">
      <button type="submit">Subscribe</button>
    </form>
    <a href="/broken">Broken Link</a>
    <form method="post" action="/items">
      <input type="text" name="name">
      <input type="text" name="quantity">
      <button type="submit">Add item</button>
    </form>
    <button id="load-items" onclick="fetch('/api/items')">Load items (API)</button>
    <button id="wishlist">Wishlist</button>
    <button id="recently-viewed">Recently viewed</button>
    <a href="#Reports">Reports</a>
    <a href="#Analytics">Analytics</a>
    <div id="hash-reports" style="display:none">
      <h2>Reports</h2>
      <a href="/settings">Settings (only reachable from the Reports hash view)</a>
    </div>
    <div id="hash-analytics" style="display:none">
      <h2>Analytics</h2>
      <a href="/cart">Cart (only reachable from the Analytics hash view)</a>
    </div>
    <script>
      // Reproduces a hash-routed SPA (e.g. an Angular/React app, including
      // WaveMaker-generated ones) where distinct "pages" are swapped by
      // client-side JS reacting to location.hash, never a server round-trip.
      function renderHashView() {{
        document.getElementById('hash-reports').style.display =
          location.hash === '#Reports' ? 'block' : 'none';
        document.getElementById('hash-analytics').style.display =
          location.hash === '#Analytics' ? 'block' : 'none';
      }}
      window.addEventListener('hashchange', renderHashView);
      renderHashView();
    </script>
    </body></html>
    """


@app.get("/login", response_class=HTMLResponse)
def login_page() -> str:
    return """
    <html><body>
    <form method="post" action="/login">
      <input type="text" name="username">
      <input type="password" name="password">
      <button type="submit">Log in</button>
    </form>
    </body></html>
    """


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    token = str(uuid.uuid4())
    _valid_sessions.add(token)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("session", token)
    return response


@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    """Reachable from the dashboard's "Account" dropdown (`revealAccountMenu`,
    a real `<a href="/logout">`) — the crawler must never follow this. If it
    did, this ends the session for real, exactly like a real app's logout
    would, proving the guard actually matters rather than just checking a
    label."""
    _valid_sessions.discard(request.cookies.get("session"))
    return RedirectResponse(url="/login")


@app.get("/items", response_class=HTMLResponse)
def items(request: Request) -> Response:
    if not _authenticated(request):
        # Protected routes redirect straight to the login page (not the
        # public landing page) — matches real apps, and is what lets the
        # existing redirect+password-field session-expiry heuristic still
        # fire now that `/` itself no longer carries a password field.
        return RedirectResponse(url="/login")
    # One "Edit" button per row (Story 2.2 AC 6, representative-action
    # sampling) — a repeated identical action pattern the crawler must
    # exercise once, not once per grid row.
    rows = "".join(f"<li>{item} <button>Edit</button></li>" for item in _items)
    return HTMLResponse(
        f"""<html><body>{_HEADER}<ul>{rows}</ul>
        <button onclick="window.location='/cart'">View Cart</button>
        <a href='/'>Home</a></body></html>"""
    )


@app.post("/items")
def create_item(
    request: Request, name: str = Form(...), quantity: str = Form("1")
) -> RedirectResponse:
    if _authenticated(request):
        _items.append(name)
    return RedirectResponse(url="/items", status_code=303)


@app.get("/about", response_class=HTMLResponse)
def about(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return HTMLResponse(
        f"<html><body>{_HEADER}{_APP_NAV}<p>About this app.</p><a href='/'>Home</a></body></html>"
    )


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request) -> Response:
    """A normal, directly-linked page with a password field that is *not*
    the login form — reproduces the false-positive session-expiry report
    (a change-password section, reached without any redirect)."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return HTMLResponse(
        f"""
        <html><body>
        {_APP_NAV}
        <h1>Settings</h1>
        <form method="post" action="/settings/password">
          <input type="password" name="new_password">
          <button type="submit">Change password</button>
        </form>
        <a href="/">Home</a>
        </body></html>
        """
    )


@app.get("/cart", response_class=HTMLResponse)
def cart(request: Request) -> Response:
    """Reachable only via the /items page's "View Cart" button
    (`window.location`, not an `<a href>`) — proves button-triggered
    navigation gets crawled further, not just captured as a dead-end click."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return HTMLResponse(
        f"<html><body>{_HEADER}{_APP_NAV}<h1>Cart</h1><a href='/'>Home</a></body></html>"
    )


@app.get("/order-history", response_class=HTMLResponse)
def order_history(request: Request) -> Response:
    """Reachable only via the dashboard's "Account" dropdown — an `<a>`
    toggle (not a `<button>`) whose menu items are injected into the DOM only
    on click, proving the crawler clicks dead-href anchors too, not just
    `<button>` elements."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return HTMLResponse(
        f"<html><body>{_HEADER}{_APP_NAV}<h1>Order History</h1><a href='/'>Home</a></body></html>"
    )


@app.get("/widgets", response_class=HTMLResponse)
def widgets(request: Request) -> Response:
    """Reachable only via the persistent left-nav's "Widgets" button, which
    sits *after* "Dashboard" in DOM order on every page but the dashboard
    itself — proves a navigating click doesn't stop the whole button pass."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return HTMLResponse(f"<html><body>{_HEADER}<h1>Widgets</h1><a href='/'>Home</a></body></html>")


@app.get("/api/items")
def api_items(request: Request) -> dict:
    if not _authenticated(request):
        return {"detail": "not authenticated"}
    return {"items": _items}


@app.get("/broken")
def broken(request: Request) -> Response:
    """A dead link reachable from the dashboard nav — reproduces a real site's
    stale/broken link (or a GET against a POST-only route, e.g. Shopbit's
    `/register` returning 405) so the crawler must prove it never persists an
    error-status destination as a real Page."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return Response(status_code=404, content="Not Found")
