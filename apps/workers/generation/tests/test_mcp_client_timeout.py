"""PlaywrightMCPClient.call_tool — timeout behavior only, no real subprocess.

`[FIXED]` regression: a stuck MCP tool call used to hang forever, eating the
whole activity's 2-minute heartbeat_timeout and killing the entire
exploration. It must now time out well before that and return the same
recoverable "(tool call failed: ...)" string other tool failures already do.
"""

import asyncio

import pytest
from generation_worker.live_exploration.mcp_client import PlaywrightMCPClient


class _HangingSession:
    async def call_tool(self, name: str, args: dict) -> None:
        await asyncio.sleep(3600)


async def test_call_tool_times_out_instead_of_hanging_forever(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "generation_worker.live_exploration.mcp_client._TOOL_CALL_TIMEOUT_SECONDS", 0.05
    )
    client = PlaywrightMCPClient()
    client._session = _HangingSession()  # bypass __aenter__ — no real subprocess needed

    result = await asyncio.wait_for(client.call_tool("browser_snapshot", {}), timeout=2)

    assert "timed out" in result


def test_spawns_with_a_real_desktop_viewport_size() -> None:
    """`[FIXED]` regression: no explicit size left the spawned browser at
    whatever small default `@playwright/mcp` picks headless — observed live:
    a real target app's own "please use a desktop browser" gate blocked the
    agent for its entire turn budget because the viewport read as narrower
    than the app's declared breakpoint.

    `[FIXED]` Must match Playwright's own `devices['Desktop Chrome']`
    viewport (1280x720) exactly — real test execution always runs under
    that preset, and a captured/healed locator for anything
    viewport-dependent (e.g. a dropdown's positioning) was observed live to
    keep failing only during real execution, never during explore/heal at a
    different, unmatched size."""
    client = PlaywrightMCPClient()

    args = client._server_params.args
    assert "--viewport-size" in args
    assert args[args.index("--viewport-size") + 1] == "1280x720"
