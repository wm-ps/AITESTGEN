"""`[FIXED]` root-cause fix: `_build_auth_setup_script` received discovered
`LoginPageEvidence.username_locator`/`.password_locator` but only ever read
`.url` — the generated `auth.setup.ts` went straight from `page.goto()` to
`fillCredentials()` with no readiness wait, then leaned on a `networkidle`
wait *after* submit as its only settle signal. `networkidle` never reliably
fires against a real SPA (background polling/analytics/websockets), and a
readiness wait *before* filling was missing entirely — exactly the two things
Discovery's own crawler (`discovery_worker/session.py`) does that generated
execution didn't. Fixed by waiting on the same discovered password-field
locator `fillCredentials` already fills, with a bounded 2-attempt retry on
navigation, an already-authenticated short-circuit, and no `networkidle`
anywhere in the flow.
"""

from test_suite_assembler.assembler import (
    LoginPageEvidence,
    _build_auth_setup_script,
    _build_playwright_config,
)

EVIDENCE = LoginPageEvidence(
    url="https://acme.example.com/login",
    username_locator="page.locator('#username').first()",
    password_locator="page.locator('#password').first()",
)


def test_setup_project_gets_a_longer_timeout_than_playwright_default() -> None:
    config = _build_playwright_config("https://acme.example.com", has_login=True)

    assert "name: 'setup'" in config
    assert "timeout: 60000" in config


def test_auth_setup_never_uses_networkidle() -> None:
    # (A) fast path / (G) discovered evidence: no networkidle *wait call*
    # anywhere — the generic signal that never reliably fires against a real
    # SPA. (The word itself may still appear in an explanatory comment.)
    script = _build_auth_setup_script("standard_login", login_evidence=EVIDENCE)

    assert "waitForLoadState" not in script
    assert "'networkidle'" not in script


def test_auth_setup_waits_on_discovered_password_field_before_filling() -> None:
    # (B) slow login UI: readiness is a `waitFor` on the real discovered
    # locator, not a fixed sleep or networkidle.
    script = _build_auth_setup_script("standard_login", login_evidence=EVIDENCE)

    assert "const passwordField = page.locator('#password').first()" in script
    assert "passwordField\n      .waitFor({ state: 'visible', timeout: 5000 })" in script
    assert "waitForTimeout" not in script


def test_auth_setup_falls_back_to_generic_password_selector_without_evidence() -> None:
    # No hardcoded app-specific selector — only the existing generic
    # fallback, same one _build_auth_helper_script already uses.
    script = _build_auth_setup_script("standard_login", login_evidence=None)

    assert 'input[type="password"]' in script


def test_auth_setup_retries_navigation_bounded_not_unbounded() -> None:
    # (C)/(D) nav timeout: bounded retry (2 attempts), not an unbounded loop
    # and not the crawler's much larger heartbeat-backed budget.
    script = _build_auth_setup_script("standard_login", login_evidence=EVIDENCE)

    assert "attempt < 2" in script
    assert "goto(loginUrl, { timeout: 10000 })" in script


def test_auth_setup_throws_clearly_when_login_never_becomes_ready() -> None:
    # (D)/(E): a genuine failure must throw, never swallow like the
    # crawler's tolerant `except Exception: pass`.
    script = _build_auth_setup_script("standard_login", login_evidence=EVIDENCE)

    assert "throw new Error(" in script
    assert "could not reach a login form" in script
    assert "still on the login page" in script


def test_auth_setup_detects_already_authenticated_state() -> None:
    # (F): an already-authenticated session must skip fillCredentials
    # entirely rather than re-logging in.
    script = _build_auth_setup_script("standard_login", login_evidence=EVIDENCE)

    assert "alreadyAuthenticated" in script
    assert "if (!alreadyAuthenticated) {" in script


if __name__ == "__main__":
    test_setup_project_gets_a_longer_timeout_than_playwright_default()
    test_auth_setup_never_uses_networkidle()
    test_auth_setup_waits_on_discovered_password_field_before_filling()
    test_auth_setup_falls_back_to_generic_password_selector_without_evidence()
    test_auth_setup_retries_navigation_bounded_not_unbounded()
    test_auth_setup_throws_clearly_when_login_never_becomes_ready()
    test_auth_setup_detects_already_authenticated_state()
    print("ok")
