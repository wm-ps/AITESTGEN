"""RemoteDisplayBackend — the internal interface behind this feature's
remote-desktop transport (plan round 2: kept swappable for a lower-latency
transport later without touching session-lifecycle/persistence code).

`NoVncDisplayBackend` is the only implementation for the MVP: `Xvfb` + one
raw VNC (RFB) server, `x11vnc`.

ponytail: the plan's classic-noVNC-stack description also names a separate
`websockify` process; this implementation folds that into `app.py`'s own
`/vnc` websocket handler instead — a plain `asyncio.open_connection`
TCP<->websocket byte-pump to `x11vnc`'s local RFB port, since it's a small,
well-understood job (exactly websockify's own) and one fewer subprocess to
isolate/clean up per session. `x11vnc` is bound `-localhost` regardless — it
is never reachable except through that one proxy. Revisit with a real
`websockify` process if this service ever needs to proxy VNC traffic
somewhere other than its own `/vnc` route (e.g. a standalone display-proxy
deployment), since folding it in only works while the pump and the
authenticated route are the same process.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from pathlib import Path
from typing import Protocol


class DisplayStartError(Exception):
    """Xvfb or x11vnc failed to start for this session."""


class RemoteDisplayBackend(Protocol):
    @property
    def vnc_port(self) -> int: ...

    @property
    def display_env(self) -> str:
        """The `DISPLAY` value (e.g. ':100') the recording browser/Codegen
        process must be launched with to appear on this session's display."""
        ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class NoVncDisplayBackend:
    def __init__(
        self,
        *,
        display: int,
        vnc_port: int,
        session_dir: Path,
        viewport: tuple[int, int],
    ) -> None:
        self._display = display
        self._vnc_port = vnc_port
        self._session_dir = session_dir
        self._viewport = viewport
        self._xvfb: asyncio.subprocess.Process | None = None
        self._x11vnc: asyncio.subprocess.Process | None = None

    @property
    def vnc_port(self) -> int:
        return self._vnc_port

    @property
    def display_env(self) -> str:
        return f":{self._display}"

    async def start(self) -> None:
        try:
            await self._start()
        except BaseException:
            # A failure partway through (e.g. x11vnc failing after Xvfb
            # already came up) must not leak the already-started process(es)
            # — an orphaned Xvfb holds its display's X11 socket/lock file
            # forever, so every later session that lands on the same
            # (by-then-released-in-the-allocator) display number fails too,
            # with the confusing "Xvfb exited immediately" from a completely
            # unrelated attempt. `stop()` already no-ops safely on whichever
            # of `_xvfb`/`_x11vnc` never got created.
            if self._xvfb is not None:
                await self.stop()
            raise

    async def _start(self) -> None:
        width, height = self._viewport
        self._session_dir.mkdir(parents=True, exist_ok=True)
        # preexec_fn=setpgid(0, 0): makes Xvfb's own pid the pgid every
        # sibling process below joins (via `preexec_fn=setpgid(0, this
        # pid)`, see x11vnc/Codegen), so `stop()` can signal the whole tree
        # atomically with one killpg — WITHOUT starting a new *session*
        # (unlike `start_new_session=True`/setsid(), which was tried first
        # and broke x11vnc's own setpgid below: POSIX forbids joining a
        # process group that belongs to a different session, and setsid()
        # would put Xvfb in a session of its own). Not the newer
        # `process_group=0` stdlib kwarg (Python 3.11+) either — this
        # service's actual event loop is uvloop (pulled in by
        # `uvicorn[standard]`), whose subprocess_exec rejects that kwarg
        # outright (confirmed against its own loop.pyx: only `preexec_fn`/
        # `start_new_session` are supported), which was silently failing
        # every single recording session until this fix.
        self._xvfb = await asyncio.create_subprocess_exec(
            "Xvfb",
            self.display_env,
            "-screen",
            "0",
            f"{width}x{height}x24",
            "-ac",
            "-nolisten",
            "tcp",
            env={**os.environ, "XAUTHORITY": str(self._session_dir / ".Xauthority")},
            preexec_fn=lambda: os.setpgid(0, 0),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # ponytail: a fixed settle delay rather than polling for Xvfb's
        # socket to actually accept connections — simplest thing that
        # works for a screen this small; swap for a real readiness probe
        # (poll connect to the X socket) if this is ever observed flaky.
        await asyncio.sleep(0.5)
        if self._xvfb.returncode is not None:
            raise DisplayStartError(f"Xvfb exited immediately (code={self._xvfb.returncode})")

        # uvloop has no `process_group=<existing pgid>` equivalent (only
        # `start_new_session`, which always creates a *new* group) — joining
        # Xvfb's existing group needs the pre-3.11 `preexec_fn` idiom
        # instead: `setpgid(0, pgid)` in the child, before exec.
        xvfb_pgid = self._xvfb.pid
        self._x11vnc = await asyncio.create_subprocess_exec(
            "x11vnc",
            "-display",
            self.display_env,
            "-rfbport",
            str(self._vnc_port),
            "-localhost",
            "-forever",
            "-shared",
            "-quiet",
            "-nopw",
            preexec_fn=lambda: os.setpgid(0, xvfb_pgid),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Observed live: a fixed settle delay here (matching Xvfb's own
        # above) isn't always enough — `_proxy_vnc` connecting immediately
        # after this method returns sometimes hit ConnectionRefusedError
        # because x11vnc hadn't finished binding its RFB port yet. Poll for
        # actual readiness instead of guessing a delay.
        await self._wait_for_x11vnc_ready()

    async def _wait_for_x11vnc_ready(self, *, timeout: float = 5.0) -> None:
        assert self._x11vnc is not None
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        while True:
            if self._x11vnc.returncode is not None:
                raise DisplayStartError(f"x11vnc exited immediately (code={self._x11vnc.returncode})")
            try:
                _, writer = await asyncio.open_connection("127.0.0.1", self._vnc_port)
            except OSError:
                if loop.time() >= deadline:
                    raise DisplayStartError(
                        f"x11vnc did not start accepting connections on port {self._vnc_port} "
                        f"within {timeout}s"
                    ) from None
                await asyncio.sleep(0.1)
                continue
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            return

    def join_process_group(self) -> int:
        """The pgid every other subprocess for this session (Codegen
        included) must join (`preexec_fn=lambda: os.setpgid(0, this)`) so
        `stop()`'s single killpg tears the whole tree down together."""
        assert self._xvfb is not None
        return self._xvfb.pid

    async def stop(self) -> None:
        assert self._xvfb is not None
        pgid = self._xvfb.pid
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGTERM)
        for proc in (self._x11vnc, self._xvfb):
            if proc is None:
                continue
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=5)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)
