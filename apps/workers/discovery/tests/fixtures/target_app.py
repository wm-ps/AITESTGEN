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
# Story 2.16 Task 5: a linear 3-step wizard — step-a creates a real
# business record (like a real "place an order" submit), step-b is a plain
# waypoint, step-c has a required business-specific field that always
# defers. Resuming must never replay step-a (the record-creating step).
_wizard_orders: list[str] = []


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
    # `.clear()`, not reassignment — a test that imports this list by name
    # (`from fixtures.target_app import _wizard_orders`) holds a reference to
    # the *same* list object; reassigning this global here would leave that
    # import pointing at a stale, no-longer-current list.
    _wizard_orders.clear()


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
    <a href="/server-error">Server Error Link</a>
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


@app.get("/frames", response_class=HTMLResponse)
def frames_page(request: Request) -> Response:
    """Story 2.14 AC 1 — a same-origin iframe with its own form, plus a
    cross-origin one. The cross-origin frame points at the *same* server
    under the `localhost` hostname rather than `127.0.0.1` — different
    origin per RFC 6454 (host differs) even though it's the identical
    process, so the test stays fast/deterministic without a second server."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    port = request.url.port
    return HTMLResponse(
        f"""
        <html><body>
        <h1>Frames</h1>
        <iframe title="same-origin" src="/frame-content"></iframe>
        <iframe title="cross-origin" src="http://localhost:{port}/frame-content"></iframe>
        </body></html>
        """
    )


@app.get("/frame-content", response_class=HTMLResponse)
def frame_content(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """<html><body>
        <form method="post" action="/items"><input type="text" name="name">
        <button type="submit">Add from frame</button></form>
        <button id="frame-button">Frame button</button>
        </body></html>"""
    )


@app.get("/shadow-dom", response_class=HTMLResponse)
def shadow_dom_page(request: Request) -> Response:
    """Story 2.14 AC 2 — one custom element with an open shadow root
    containing a button, one with a closed root (genuinely opaque, must be
    logged as unreachable rather than found)."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """
        <html><body>
        <h1>Shadow DOM</h1>
        <open-widget></open-widget>
        <closed-widget></closed-widget>
        <script>
          customElements.define('open-widget', class extends HTMLElement {
            connectedCallback() {
              const root = this.attachShadow({ mode: 'open' });
              root.innerHTML = '<button>Shadow button</button>';
            }
          });
          customElements.define('closed-widget', class extends HTMLElement {
            connectedCallback() {
              const root = this.attachShadow({ mode: 'closed' });
              root.innerHTML = '<button>Hidden button</button>';
            }
          });
        </script>
        </body></html>
        """
    )


@app.get("/tabs", response_class=HTMLResponse)
def tabs_page(request: Request) -> Response:
    """Story 2.14 AC 3 — a plain ARIA tablist/tab pattern."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """
        <html><body>
        <h1>Tabs</h1>
        <div role="tablist">
          <button role="tab" onclick="setPanel('First panel')">First</button>
          <button role="tab" onclick="setPanel('Second panel')">Second</button>
        </div>
        <script>function setPanel(t) { document.getElementById('panel').innerText = t; }</script>
        <div id="panel">First panel</div>
        </body></html>
        """
    )


@app.get("/dialog", response_class=HTMLResponse)
def dialog_page(request: Request) -> Response:
    """Story 2.14 AC 4 — a closable, ARIA-correct dialog and a deliberately
    unclosable one (no working close control, Escape does nothing) to prove
    the forced-navigation fallback fires rather than stranding the run."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """
        <html><body>
        <h1>Dialog</h1>
        <button onclick="showDialog('good-dialog')">Open dialog</button>
        <button onclick="showDialog('stuck-dialog')">Open stuck dialog</button>
        <script>
          function showDialog(id) { document.getElementById(id).style.display = 'block'; }
          function hideDialog(id) { document.getElementById(id).style.display = 'none'; }
        </script>
        <div id="good-dialog" role="dialog" aria-modal="true" style="display:none">
          <p>A dialog</p>
          <button onclick="hideDialog('good-dialog')">Close</button>
        </div>
        <div id="stuck-dialog" role="dialog" aria-modal="true" style="display:none">
          <p>Cannot be closed</p>
        </div>
        </body></html>
        """
    )


@app.get("/popups", response_class=HTMLResponse)
def popups_page(request: Request) -> Response:
    """Story 2.14 AC 5 — a same-origin popup (followed) and a cross-origin
    one (flagged), using the same `localhost` vs `127.0.0.1` origin trick as
    `/frames`."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    port = request.url.port
    return HTMLResponse(
        f"""
        <html><body>
        <h1>Popups</h1>
        <button onclick="window.open('/items', '_blank')">Open same-origin popup</button>
        <button onclick="openCrossOrigin()">Open cross-origin popup</button>
        <script>
          function openCrossOrigin() {{
            window.open('http://localhost:{port}/items', '_blank');
          }}
        </script>
        </body></html>
        """
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request) -> Response:
    """Story 2.14 AC 6 — a plain file-upload field."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """<html><body><h1>Upload</h1>
        <form method="post" action="/items"><input type="file" name="doc">
        <button type="submit">Upload</button></form>
        <a href="/">Home</a></body></html>"""
    )


_stuck_visit_count = 0


@app.get("/stuck", response_class=HTMLResponse)
def stuck_page(request: Request) -> Response:
    """Story 2.11 — a state that no return rung can reconstruct: every
    visit renders a different heading (a visit counter), simulating an
    application that holds state server-side with no deep-linkable URL
    (ASP.NET WebForms postback, a server-driven wizard). Proves the State
    Return ladder gives up honestly (rung 5, `unreached`) rather than
    silently accepting a wrong landing or retrying forever."""
    global _stuck_visit_count
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    _stuck_visit_count += 1
    return HTMLResponse(
        f"""<html><body><h1>Stuck {_stuck_visit_count}</h1>
        <button onclick="window.location='/stuck-away'">Leave</button>
        <button>Second button</button>
        </body></html>""",
        # Forces a fresh server hit on browser back-navigation too — the
        # visit counter above is the whole point of this fixture (Story
        # 2.11), and a cached bfcache render would silently defeat it.
        headers={"Cache-Control": "no-store"},
    )


@app.get("/stuck-away", response_class=HTMLResponse)
def stuck_away_page(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse("<html><body><h1>Away</h1></body></html>")


@app.get("/records/{record_id}", response_class=HTMLResponse)
def records_page(record_id: int, request: Request) -> Response:
    """Story 2.10 — three numeric-id pages sharing one route template
    (`/records/{id}`). Record 2 shows Approve/Reject instead of Edit/Submit
    (a materially different state -> VARIANT); record 3 is identical to
    record 1 (-> SAME). Linked from record 1 so a crawl starting there
    discovers all three via plain BFS."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    if record_id == 2:
        actions = '<button>Approve</button><button>Reject</button>'
    else:
        actions = '<button>Edit</button><button>Submit</button>'
    links = ""
    if record_id == 1:
        links = '<a href="/records/2">Record 2</a><a href="/records/3">Record 3</a>'
    return HTMLResponse(
        f"<html><body><h1>Record</h1>{actions}{links}</body></html>"
    )


@app.get("/locators", response_class=HTMLResponse)
def locators_page(request: Request) -> Response:
    """Story 2.21 — one button per capture tier: a real `data-testid`, a
    button whose only class is a CSS-in-JS-style hash but has a real ARIA
    role+name (must rank the role above the hash), and a bare `div` with an
    `onclick` and nothing else distinguishing (falls through to a CSS path).

    `[ADDED]` locator-accuracy fix — an unlabeled `<input>` pre-filled with a
    value (reproducing a real target's own pre-set example/default, or a
    value discovery itself typed in before ever capturing this element) but
    carrying a real `name` attribute: must never surface its current
    `.value` as an "aria" name candidate, and must surface `[name="..."]` as
    a durable candidate instead of falling through straight to the fragile
    absolute path. A second, placeholder-only input (no value, no label):
    its placeholder is a legitimate but explicitly fragile "aria" candidate.
    A third input has NO id/name/label/placeholder at all but a pre-filled
    value — the only thing left to build any locator from besides a pure
    positional path.

    `[ADDED]` locator-priority fix — a button with a real (non-hash) class
    and visible text shared with other generic-verb controls elsewhere in a
    real app (a header "Logout" duplicated in a desktop/mobile nav, a modal,
    etc.): its `role=button[name="Logout"]` "aria" candidate must never
    outrank the real `.link-button` class, since accessible-name collisions
    on a common label are exactly the failure this must avoid."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """
        <html><body>
        <h1>Locators</h1>
        <button data-testid="save-button" onclick="void(0)">Save</button>
        <button class="css-1x2y3z" onclick="void(0)">Confirm order</button>
        <div id="bare-div" onclick="void(0)"></div>
        <input name="principal" value="500000">
        <input name="promoCode" placeholder="e.g. SAVE10">
        <input value="John Doe">
        <button type="submit" class="link-button" onclick="void(0)">Logout</button>
        </body></html>
        """
    )


@app.get("/load-more", response_class=HTMLResponse)
def load_more_page(request: Request) -> Response:
    """Story 2.9 AC 5/6 — a "Load More" button that grows the DOM a fixed
    amount per click up to a cap, entirely client-side (no server state
    needed): 3 items per click, capped at 12. Sampling must stop once
    clicking stops growing the list (the confirmed-pattern rule), not at
    the very first click and not only once the cap is hit."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """
        <html><body>
        <h1>Load More</h1>
        <div id="list"><div class="item">Item 1</div></div>
        <button id="load-more-btn">Load More</button>
        <script>
          let count = 1;
          const cap = 12;
          document.getElementById('load-more-btn').addEventListener('click', () => {
            const toAdd = Math.min(3, cap - count);
            for (let i = 0; i < toAdd; i++) {
              count++;
              const div = document.createElement('div');
              div.className = 'item';
              div.innerText = 'Item ' + count;
              document.getElementById('list').appendChild(div);
            }
          });
        </script>
        </body></html>
        """
    )


@app.get("/polling", response_class=HTMLResponse)
def polling_page(request: Request) -> Response:
    """Story 2.9 AC 1a — emits a fixed-URL poll every 300ms. Readiness must
    classify it as ignorable and settle well inside the timeout, not treat
    it as perpetual application traffic."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """<html><body><h1>Polling</h1>
        <script>setInterval(() => { fetch('/api/items'); }, 300);</script>
        </body></html>"""
    )


@app.get("/never-settles", response_class=HTMLResponse)
def never_settles_page(request: Request) -> Response:
    """Story 2.9 AC 3 — the DOM mutates continuously; readiness must give
    up at its configured ceiling rather than wait forever."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """<html><body><h1>Never settles</h1><div id="ticker"></div>
        <script>
          setInterval(() => { document.getElementById('ticker').innerText = Date.now(); }, 50);
        </script>
        </body></html>"""
    )


@app.get("/broken")
def broken(request: Request) -> Response:
    """A dead link reachable from the dashboard nav — reproduces a real site's
    stale/broken link (or a GET against a POST-only route, e.g. Shopbit's
    `/register` returning 405) so the crawler must prove it never persists an
    error-status destination as a real Page."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return Response(status_code=404, content="Not Found")


@app.get("/server-error")
def server_error(request: Request) -> Response:
    """Story 2.18 AC 2/3: a destination that always 5xxs — proves the
    crawler retries a small bounded number of times before writing a
    `DiscoveryError` (DISC-003), unlike `/broken`'s plain 404 (never
    retried, never logged as a target-application failure)."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return Response(status_code=503, content="Service Unavailable")


@app.get("/wizard/step-a", response_class=HTMLResponse)
def wizard_step_a(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """<html><body><h1>Wizard: Step A</h1>
        <form method="post" action="/wizard/step-a">
          <button type="submit">Continue</button>
        </form>
        </body></html>"""
    )


@app.post("/wizard/step-a")
def wizard_step_a_submit(request: Request) -> RedirectResponse:
    if _authenticated(request):
        # Reproduces a real order-creating intermediate step — resume must
        # never replay this (Story 2.16 AC 3/Task 5's specific regression).
        _wizard_orders.append(f"order-{len(_wizard_orders) + 1}")
    return RedirectResponse(url="/wizard/step-b", status_code=303)


@app.get("/wizard/step-b", response_class=HTMLResponse)
def wizard_step_b(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """<html><body><h1>Wizard: Step B</h1>
        <a href="/wizard/step-c">Continue to Step C</a>
        </body></html>"""
    )


@app.get("/wizard/step-c", response_class=HTMLResponse)
def wizard_step_c(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse(url="/login")
    return HTMLResponse(
        """<html><body><h1>Wizard: Step C</h1>
        <form method="post" action="/wizard/step-c">
          <input type="text" name="Policy Number" required>
          <button type="submit">Submit</button>
        </form>
        </body></html>"""
    )


@app.post("/wizard/step-c")
def wizard_step_c_submit(request: Request) -> RedirectResponse:
    return RedirectResponse(url="/wizard/step-c", status_code=303)


@app.get("/safety-test", response_class=HTMLResponse)
def safety_test(request: Request) -> Response:
    """Story 2.12 Task 6: one button per classification bucket, none of
    which navigate — proves the Safety Engine's verdict (never the DOM
    itself) is what determines whether a click actually happens."""
    if not _authenticated(request):
        return RedirectResponse(url="/login")  # see /items for why
    return HTMLResponse(
        """
        <html><body>
        <h1>Safety Test</h1>
        <button onclick="return false;">Delete</button>
        <button onclick="return false;">Submit</button>
        <button onclick="return false;">Frobnicate</button>
        </body></html>
        """
    )
