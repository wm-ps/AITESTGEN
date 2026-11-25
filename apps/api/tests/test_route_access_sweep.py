"""Every route is classified: public, organisation-level, or going through the
application access checks (`api.access`).

This replaces the old app-wide "viewer can't write" dependency, which denied by
default. Access is now decided where an application is looked up, so the guard
against a forgotten route is this test: it walks `app.routes` and fails for any
route that is none of

* PUBLIC — needs no sign-in (login, invite acceptance, password reset, health);
* ORG_LEVEL — signed in, but about the organisation or the caller rather than
  one application (team, invites, approved domains, settings, ...);
* application-scoped — its handler reaches an application through the access
  helpers, so a missing or hidden application is a 404 and a low role a 403.

Add a new route and this test tells you which of the three it is. No database
needed.
"""

import inspect
from collections.abc import Iterator
from importlib import import_module

from api.main import app
from fastapi.routing import APIRoute

PUBLIC = {
    ("GET", "/health"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("POST", "/auth/forgot-password"),
    ("GET", "/auth/reset-password"),
    ("POST", "/auth/reset-password"),
    ("POST", "/invites/accept"),
    ("POST", "/contact"),  # the public "Connect with our team" enquiry form
}

# Signed in, scoped to the caller's organisation (or the caller), not to one application.
ORG_LEVEL = {
    ("GET", "/auth/me"),
    ("POST", "/invites"),
    ("GET", "/invites"),
    ("DELETE", "/invites/{external_id}"),
    ("GET", "/team"),
    ("DELETE", "/team/{email}"),
    ("PATCH", "/team/{email}/role"),
    ("POST", "/applications"),  # creates one: the adder becomes its admin
    ("POST", "/applications/test-connection"),
    ("POST", "/applications/verify-credentials"),
    ("GET", "/applications/verify-credentials/{check_id}"),
    ("GET", "/activity"),  # super admin only (CurrentAdminDep)
    # Teams and the workspace switcher: about who is in which team, not one application.
    ("GET", "/me/workspaces"),
    ("PATCH", "/me/workspace"),
    ("GET", "/teams"),
    ("POST", "/teams"),
    ("GET", "/teams/{external_id}"),
    ("DELETE", "/teams/{external_id}"),
    ("GET", "/teams/{external_id}/members"),
    ("POST", "/teams/{external_id}/members"),
    ("PATCH", "/teams/{external_id}/members/{email}"),
    ("DELETE", "/teams/{external_id}/members/{email}"),
    ("GET", "/teams/{external_id}/applications"),
    ("GET", "/team/{email}/removal-impact"),
    ("POST", "/team/step-down"),
    ("GET", "/organization/limits"),
    ("PUT", "/organization/limits"),
    ("GET", "/settings"),
    ("PATCH", "/settings"),
    ("GET", "/explorer/settings"),
    ("PUT", "/explorer/settings"),
    ("POST", "/admin/cleanup/run"),
    ("POST", "/admin/reconcile-stale-runs/run"),
    ("GET", "/domains"),
    ("POST", "/domains"),
    ("DELETE", "/domains/{external_id}"),
    ("POST", "/domains/check"),
}

# Routes whose handler hands the whole job to another handler that does the check.
DELEGATES = {("GET", "/explorer/runs/{run_id}/report/download"): "report"}

# Source text that shows a handler goes through the access checks.
ACCESS_MARKERS = (
    "_get_org_application(",
    "_org_application(",
    "_owned_application(",
    "_owned_run(",
    "_owned_mission(",
    "_owned_question(",
    "_owned_test(",
    "_get_org_journey(",
    "_get_org_scenario(",
    "_get_org_schedule(",
    "_get_org_test_asset(",
    "_get_org_test_data_entry(",
    "_get_collection(",
    "_managed_application(",
    "require_application(",
    "visibility_clause(",
    "admin_clause(",
)

_DOCS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
_AUTH_CALLS = {"current_user", "current_org_id", "require_admin"}


def _walk(routes: list, prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    """Every APIRoute with its full path — FastAPI keeps included routers as
    `_IncludedRouter` objects (prefix in `include_context`), so recurse into them."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
        elif hasattr(route, "original_router"):
            yield from _walk(route.original_router.routes, prefix + (route.include_context.prefix or ""))


def _routes() -> list[tuple[str, str, APIRoute]]:
    found = []
    for path, route in _walk(app.routes):
        if path not in _DOCS:
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                found.append((method, path, route))
    return found


def _depends_on_sign_in(route: APIRoute) -> bool:
    stack = [route.dependant]
    while stack:
        dependant = stack.pop()
        if getattr(dependant.call, "__name__", "") in _AUTH_CALLS:
            return True
        stack.extend(dependant.dependencies)
    return False


def test_every_route_is_public_org_level_or_goes_through_the_access_checks() -> None:
    unclassified = []
    for method, path, route in _routes():
        key = (method, path)
        if key in PUBLIC or key in ORG_LEVEL:
            continue
        handler = getattr(import_module(route.endpoint.__module__), DELEGATES[key]) if key in DELEGATES else route.endpoint
        if not any(marker in inspect.getsource(handler) for marker in ACCESS_MARKERS):
            unclassified.append(f"{method} {path}")
    assert not unclassified, (
        "These routes reach no application through api.access and are not listed as PUBLIC or "
        "ORG_LEVEL in this test — classify them:\n  " + "\n  ".join(unclassified)
    )


def test_only_public_routes_skip_sign_in() -> None:
    open_routes = [
        f"{method} {path}"
        for method, path, route in _routes()
        if (method, path) not in PUBLIC and not _depends_on_sign_in(route)
    ]
    assert not open_routes, "These routes need no sign-in but are not PUBLIC:\n  " + "\n  ".join(open_routes)


def test_the_lists_do_not_name_routes_that_no_longer_exist() -> None:
    existing = {(method, path) for method, path, _ in _routes()}
    stale = sorted((PUBLIC | ORG_LEVEL | set(DELEGATES)) - existing)
    assert not stale, f"remove from the allowlists: {stale}"
