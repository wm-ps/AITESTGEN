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
_items: list[str] = ["Sample item"]
_request_count = 0
_expire_after: int | None = None


def configure(expire_after: int | None) -> None:
    """Test-only: force session expiry after N authenticated requests."""
    global _expire_after, _request_count
    _expire_after = expire_after
    _request_count = 0


def _authenticated(request: Request) -> bool:
    global _request_count
    token = request.cookies.get("session")
    if token not in _valid_sessions:
        return False
    _request_count += 1
    if _expire_after is not None and _request_count > _expire_after:
        _valid_sessions.discard(token)
        return False
    return True


# A shared header on every authenticated page, reproducing a real
# false-loop report: a nameless-input, action="#" form (e.g. a quick-search
# icon). Method defaults to GET (as real search boxes are), and the input
# has no `name` so the browser's submission carries no query string at all —
# it just re-requests the current page with a "#" fragment appended. The
# crawler must not treat that as a new page.
_HEADER = """<form action="#"><input type="text"></form>"""


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> str:
    if not _authenticated(request):
        return """
        <html><body>
        <form method="post" action="/login">
          <input type="text" name="username">
          <input type="password" name="password">
          <button type="submit">Log in</button>
        </form>
        </body></html>
        """
    return f"""
    <html><body>
    {_HEADER}
    <h1>Dashboard</h1>
    <a href="/items">Items</a>
    <a href="/about">About</a>
    <a href="/settings">Settings</a>
    <form method="post" action="/items">
      <input type="text" name="name">
      <button type="submit">Add item</button>
    </form>
    <button id="load-items" onclick="fetch('/api/items')">Load items (API)</button>
    </body></html>
    """


@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    token = str(uuid.uuid4())
    _valid_sessions.add(token)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("session", token)
    return response


@app.get("/items", response_class=HTMLResponse)
def items(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse(url="/")
    rows = "".join(f"<li>{item}</li>" for item in _items)
    return HTMLResponse(f"<html><body>{_HEADER}<ul>{rows}</ul><a href='/'>Home</a></body></html>")


@app.post("/items")
def create_item(request: Request, name: str = Form(...)) -> RedirectResponse:
    if _authenticated(request):
        _items.append(name)
    return RedirectResponse(url="/items", status_code=303)


@app.get("/about", response_class=HTMLResponse)
def about(request: Request) -> Response:
    if not _authenticated(request):
        return RedirectResponse(url="/")
    return HTMLResponse(
        f"<html><body>{_HEADER}<p>About this app.</p><a href='/'>Home</a></body></html>"
    )


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request) -> Response:
    """A normal, directly-linked page with a password field that is *not*
    the login form — reproduces the false-positive session-expiry report
    (a change-password section, reached without any redirect)."""
    if not _authenticated(request):
        return RedirectResponse(url="/")
    return HTMLResponse(
        """
        <html><body>
        <h1>Settings</h1>
        <form method="post" action="/settings/password">
          <input type="password" name="new_password">
          <button type="submit">Change password</button>
        </form>
        <a href="/">Home</a>
        </body></html>
        """
    )


@app.get("/api/items")
def api_items(request: Request) -> dict:
    if not _authenticated(request):
        return {"detail": "not authenticated"}
    return {"items": _items}
