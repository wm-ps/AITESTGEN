"""PlaywrightMCPClient — the one place this codebase speaks the MCP wire
protocol. Everything else (agent.py) only ever calls `call_tool`/`list_tools`
on this class; the browser itself is owned entirely by the spawned
`@playwright/mcp` subprocess, never by this Python process.
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

# Pinned, not "@latest" — an unpinned MCP server version could silently
# change tool names/argument shapes underneath the agent's fixed prompt.
# Bump deliberately, alongside the prompt, when upgrading.
_PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@0.0.41"

# `[FIXED]` A real target page can leave the spawned @playwright/mcp
# subprocess stuck (e.g. `browser_snapshot` waiting on a page that never
# settles) — with no timeout here, that hang was silent and unbounded: it
# ate the whole activity's 2-minute `heartbeat_timeout`
# (live_exploration_workflow.py) before Temporal killed the *entire*
# exploration, producing zero test cases instead of one recoverable failed
# observation. Comfortably under that 2 minutes so `observe()`'s own
# heartbeat (called right before this) still lands within its window.
_TOOL_CALL_TIMEOUT_SECONDS = 90


class PlaywrightMCPClient:
    """One exploration (or heal) session's browser, via a spawned MCP server
    subprocess. Use as an async context manager — the subprocess and its
    browser are torn down on exit regardless of how exploration ended."""

    def __init__(self, *, storage_state_path: str | None = None, headless: bool = True) -> None:
        # `[FIXED]` No explicit size left the spawned browser at whatever
        # small default `@playwright/mcp` picks headless — observed live: a
        # real target app's own "please use a desktop browser" gate blocked
        # the agent for its entire turn budget because the viewport read as
        # narrower than the app's declared 1280px breakpoint. A real desktop
        # size up front is a precondition every exploration/heal session
        # needs, not something worth guessing about per-app.
        #
        # `[FIXED]` Was 1440x900 — an arbitrary "desktop-sized" guess, not
        # matched to anything. Real test execution (`test_suite_assembler`'s
        # exported `playwright.config.ts`) always runs under Playwright's own
        # `devices['Desktop Chrome']` preset, whose viewport is exactly
        # 1280x720 — observed live: a captured/healed locator for a
        # viewport-dependent popup (a dropdown whose positioning/rendering
        # genuinely differs by available space) kept failing "not visible"
        # only during real execution, never during exploration/heal at the
        # old, different size. Explore/heal must see the exact same viewport
        # the generated test will actually run under, or anything
        # viewport-sensitive is being validated against a browser state the
        # real run never has.
        args = ["-y", _PLAYWRIGHT_MCP_PACKAGE, "--isolated", "--viewport-size", "1280x720"]
        if headless:
            args.append("--headless")
        if storage_state_path is not None:
            args.extend(["--storage-state", storage_state_path])
        self._server_params = StdioServerParameters(command="npx", args=args)
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> PlaywrightMCPClient:
        read, write = await self._stack.enter_async_context(stdio_client(self._server_params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    async def list_tool_names(self) -> list[str]:
        assert self._session is not None, "PlaywrightMCPClient used outside 'async with'"
        result = await self._session.list_tools()
        return [tool.name for tool in result.tools]

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        """Runs one MCP tool call, returning its text content joined —
        `browser_snapshot`'s ARIA outline, or a short status string for
        action tools. Never raises on an application-level tool error (a
        stale ref, a closed dialog); the returned text carries the MCP
        server's own error message so the agent can see and recover from
        it, same as an observation."""
        assert self._session is not None, "PlaywrightMCPClient used outside 'async with'"
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(name, args), timeout=_TOOL_CALL_TIMEOUT_SECONDS
            )
        except TimeoutError:
            logger.warning(
                "PlaywrightMCPClient: call_tool(%s) timed out after %ss",
                name,
                _TOOL_CALL_TIMEOUT_SECONDS,
            )
            return f"(tool call failed: timed out after {_TOOL_CALL_TIMEOUT_SECONDS}s)"
        except Exception as exc:
            logger.warning("PlaywrightMCPClient: call_tool(%s) transport error: %s", name, exc)
            return f"(tool call failed: {exc})"
        parts = [block.text for block in result.content if getattr(block, "text", None)]
        return "\n".join(parts)
