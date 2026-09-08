"""`run_live_inspection` — self-heal's targeted live Playwright inspection.
Real `async_playwright`/Chromium is mocked throughout (no real browser
needed for these): what's verified is the *contract* — auth-session reuse
(never a fresh login), page scoping, the function's own bounded timeout
independent of anything else, and that a failure/timeout is swallowed
(best-effort, matching `_fetch_latest_screenshot_sync`'s existing
tolerance) rather than raised into the heal loop.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from execution_worker.live_inspection import (
    LiveInspectionResult,
    _live_inspection_enabled,
    run_live_inspection,
)


class _FakeLocator:
    def __init__(self, aria_snapshot: str = "- document [ref=e1]:") -> None:
        self.aria_snapshot = AsyncMock(return_value=aria_snapshot)


class _FakePage:
    def __init__(self, url: str = "https://app.example.com/") -> None:
        self.goto = AsyncMock()
        self.title = AsyncMock(return_value="Checkout")
        self.url = url
        self.frames: list[object] = []
        self._locator = _FakeLocator()
        self.locator = MagicMock(return_value=self._locator)


class _FakeContext:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.close = AsyncMock()

    async def new_page(self) -> _FakePage:
        return self._page


class _FakeBrowser:
    def __init__(self, context: _FakeContext) -> None:
        self._context = context
        self.new_context = AsyncMock(return_value=context)
        self.close = AsyncMock()


def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch, browser: _FakeBrowser) -> None:
    fake_chromium = MagicMock()
    fake_chromium.launch = AsyncMock(return_value=browser)

    class _FakePlaywrightContextManager:
        async def __aenter__(self) -> MagicMock:
            playwright = MagicMock()
            playwright.chromium = fake_chromium
            return playwright

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(
        "execution_worker.live_inspection.async_playwright",
        lambda: _FakePlaywrightContextManager(),
    )


@pytest.mark.asyncio
async def test_reuses_existing_storage_state_and_never_logs_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    auth_dir = tmp_path / ".auth"
    auth_dir.mkdir()
    state_file = auth_dir / "state.json"
    state_file.write_text('{"cookies": [{"name": "session", "value": "abc"}]}', encoding="utf-8")

    page = _FakePage(url="https://app.example.com/checkout")
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    _install_fake_playwright(monkeypatch, browser)

    monkeypatch.setattr(
        "execution_worker.live_inspection.extract_page_locator_snapshot",
        AsyncMock(
            return_value=[
                {"strategy": "testid", "value": '[data-testid="x"]', "element_tag": "button"}
            ]
        ),
    )
    result = await run_live_inspection(
        project_dir=tmp_path, target_url="https://app.example.com/checkout"
    )

    assert result is not None
    assert result.url == "https://app.example.com/checkout"
    browser.new_context.assert_awaited_once_with(storage_state=str(state_file))
    # Exactly one navigation, to the target page — never a login/auth URL.
    page.goto.assert_awaited_once()
    goto_args, goto_kwargs = page.goto.await_args
    assert goto_args[0] == "https://app.example.com/checkout"
    context.close.assert_awaited_once()
    browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_auth_file_still_completes_without_storage_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = _FakePage()
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    _install_fake_playwright(monkeypatch, browser)
    monkeypatch.setattr(
        "execution_worker.live_inspection.extract_page_locator_snapshot",
        AsyncMock(return_value=[]),
    )

    result = await run_live_inspection(project_dir=tmp_path, target_url="https://app.example.com/")

    assert result is not None
    browser.new_context.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_respects_its_own_timeout_independent_of_a_hanging_navigation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def _hang(*args: object, **kwargs: object) -> None:
        await asyncio.sleep(999)

    page = _FakePage()
    page.goto = AsyncMock(side_effect=_hang)
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    _install_fake_playwright(monkeypatch, browser)

    result = await run_live_inspection(
        project_dir=tmp_path, target_url="https://app.example.com/", timeout_seconds=1
    )

    assert result is None


@pytest.mark.asyncio
async def test_returns_none_instead_of_raising_on_any_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_chromium = MagicMock()
    fake_chromium.launch = AsyncMock(side_effect=RuntimeError("browser failed to launch"))

    class _BrokenPlaywrightContextManager:
        async def __aenter__(self) -> MagicMock:
            playwright = MagicMock()
            playwright.chromium = fake_chromium
            return playwright

        async def __aexit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(
        "execution_worker.live_inspection.async_playwright",
        lambda: _BrokenPlaywrightContextManager(),
    )

    result = await run_live_inspection(project_dir=tmp_path, target_url="https://app.example.com/")

    assert result is None


def test_kill_switch_defaults_to_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXECUTION_WORKER_LIVE_INSPECTION_ENABLED", raising=False)
    assert _live_inspection_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", "FALSE"])
def test_kill_switch_can_be_disabled(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("EXECUTION_WORKER_LIVE_INSPECTION_ENABLED", value)
    assert _live_inspection_enabled() is False


def test_live_inspection_result_is_a_plain_dataclass() -> None:
    result = LiveInspectionResult(url="https://x", locator_candidates=[], page_title="X")
    assert result.url == "https://x"
    assert result.frames == []
    assert result.aria_snapshot is None


class _FakeFrame:
    def __init__(self, url: str, name: str) -> None:
        self.url = url
        self.name = name


@pytest.mark.asyncio
async def test_resolved_url_reflects_a_redirect_not_the_requested_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`.url` must be the real, resolved `page.url` — not an echo of
    `target_url` — so a redirect (or the target simply being the wrong
    page) is provable from the result alone, and therefore loggable."""
    page = _FakePage(url="https://app.example.com/login?redirected=1")
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    _install_fake_playwright(monkeypatch, browser)
    monkeypatch.setattr(
        "execution_worker.live_inspection.extract_page_locator_snapshot",
        AsyncMock(return_value=[]),
    )

    result = await run_live_inspection(
        project_dir=tmp_path, target_url="https://app.example.com/checkout"
    )

    assert result is not None
    assert result.url == "https://app.example.com/login?redirected=1"


@pytest.mark.asyncio
async def test_captures_frame_info(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    page = _FakePage()
    page.frames = [
        _FakeFrame("https://app.example.com/checkout", ""),
        _FakeFrame("https://payments.example.com/widget", "payment-widget"),
    ]
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    _install_fake_playwright(monkeypatch, browser)
    monkeypatch.setattr(
        "execution_worker.live_inspection.extract_page_locator_snapshot",
        AsyncMock(return_value=[]),
    )

    result = await run_live_inspection(project_dir=tmp_path, target_url="https://app.example.com/")

    assert result is not None
    assert result.frames == [
        {"url": "https://app.example.com/checkout", "name": ""},
        {"url": "https://payments.example.com/widget", "name": "payment-widget"},
    ]


@pytest.mark.asyncio
async def test_captures_real_aria_snapshot_not_from_the_llm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The accessibility snapshot logged as evidence must come from
    Playwright's own `aria_snapshot(mode="ai")` — the `[ref=eN]`-annotated
    tree — never a re-description by the LLM."""
    page = _FakePage()
    page._locator.aria_snapshot = AsyncMock(
        return_value='- button "plus Add connection" [ref=e99]:\n  - img "plus" [ref=e101]'
    )
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    _install_fake_playwright(monkeypatch, browser)
    monkeypatch.setattr(
        "execution_worker.live_inspection.extract_page_locator_snapshot",
        AsyncMock(return_value=[]),
    )

    result = await run_live_inspection(project_dir=tmp_path, target_url="https://app.example.com/")

    assert result is not None
    assert result.aria_snapshot == (
        '- button "plus Add connection" [ref=e99]:\n  - img "plus" [ref=e101]'
    )
    page.locator.assert_called_once_with("html")
    page._locator.aria_snapshot.assert_awaited_once_with(mode="ai")


@pytest.mark.asyncio
async def test_aria_snapshot_failure_degrades_to_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = _FakePage()
    page._locator.aria_snapshot = AsyncMock(side_effect=RuntimeError("snapshot failed"))
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    _install_fake_playwright(monkeypatch, browser)
    monkeypatch.setattr(
        "execution_worker.live_inspection.extract_page_locator_snapshot",
        AsyncMock(return_value=[]),
    )

    result = await run_live_inspection(project_dir=tmp_path, target_url="https://app.example.com/")

    assert result is not None
    assert result.aria_snapshot is None


@pytest.mark.asyncio
async def test_logs_requested_and_resolved_url_distinctly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Explicit regression for the exact requirement: the log must name
    `requested_url` and `resolved_url` separately (not just print one
    value), and the candidate/aria evidence logged must be this call's own
    observations, never Discovery's cached known_pages/known_locators
    (which this function is never even given — it only takes
    project_dir/target_url)."""
    import logging

    caplog.set_level(logging.INFO, logger="execution_worker.live_inspection")
    page = _FakePage(url="https://app.example.com/actual-landing-page")
    page._locator.aria_snapshot = AsyncMock(return_value='- button "Save" [ref=e1]')
    context = _FakeContext(page)
    browser = _FakeBrowser(context)
    _install_fake_playwright(monkeypatch, browser)
    monkeypatch.setattr(
        "execution_worker.live_inspection.extract_page_locator_snapshot",
        AsyncMock(
            return_value=[
                {"strategy": "aria", "value": 'role=button[name="Save"]', "element_tag": "button"}
            ]
        ),
    )

    await run_live_inspection(
        project_dir=tmp_path, target_url="https://app.example.com/requested-page"
    )

    combined = "\n".join(caplog.messages)
    assert "requested_url=https://app.example.com/requested-page" in combined
    assert "resolved_url=https://app.example.com/actual-landing-page" in combined
    assert "match=False" in combined
    assert 'role=button[name="Save"]' in combined
    assert '"Save" [ref=e1]' in combined
