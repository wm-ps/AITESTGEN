"""SessionRegistry — the one process-wide table of currently-active
`SessionRuntime`s, keyed by `token_hash`. Multiplexed within this single
long-running service (plan round 2: not one pod per session); the
`DisplayPortAllocator` it owns is what actually enforces "every session
gets its own display/ports, released back to the pool on cleanup, safely
reused by a later session" (plan §13).
"""

import asyncio
import logging

from domain import RecordingSession

from recording_worker.allocator import DisplayPortAllocator, ResourcePoolExhausted
from recording_worker.runtime import SessionRuntime

logger = logging.getLogger(__name__)


class RecordingServiceBusy(Exception):
    """Every display slot is in use — the caller should reject the
    websocket connect with a capacity error rather than queue it."""


class SessionRegistry:
    def __init__(self) -> None:
        self._allocator = DisplayPortAllocator()
        self._sessions: dict[str, tuple[SessionRuntime, asyncio.Task[None]]] = {}
        self._lock = asyncio.Lock()

    async def get_or_start(self, recording_session: RecordingSession) -> SessionRuntime:
        """Idempotent: the first `vnc`/`control` connect for a token starts
        the session's process tree; a reconnect within the grace window
        (plan §3) finds the same still-running `SessionRuntime` here and
        never relaunches anything.

        Every caller — whether it's the one that actually creates the
        session, or a concurrent second connection that finds it already in
        flight — awaits the *same* `start()` task before proceeding. This
        repo's own frontend guarantees concurrent connects for a brand-new
        token (the main tab's `control` connect and the popped-out window's
        `vnc`+`control` connects all fire within milliseconds of the same
        mint) — without this, a second connection could reach `_proxy_vnc`
        before the first connection's `start()` had actually finished
        spawning `x11vnc`, producing a spurious `ConnectionRefusedError` on
        an otherwise perfectly healthy session (observed live: the video
        connection loses the race and gets rejected while the control
        connection, started a moment later, wins it)."""
        created = False
        async with self._lock:
            existing = self._sessions.get(recording_session.token_hash)
            if existing is not None:
                runtime, start_task = existing
            else:
                try:
                    resources = self._allocator.acquire()
                except ResourcePoolExhausted as exc:
                    raise RecordingServiceBusy(str(exc)) from exc

                runtime = SessionRuntime(
                    recording_session=recording_session,
                    allocator=self._allocator,
                    resources=resources,
                    on_finished=self._on_finished,
                )
                start_task = asyncio.create_task(runtime.start())
                self._sessions[recording_session.token_hash] = (runtime, start_task)
                created = True

        try:
            await start_task
        except Exception:
            if created:
                logger.exception(
                    "recording session %s: failed to start", recording_session.external_id
                )
                self._on_finished(recording_session.token_hash)
                self._allocator.release(resources.display)
            raise
        return runtime

    def get(self, token_hash: str) -> SessionRuntime | None:
        existing = self._sessions.get(token_hash)
        return existing[0] if existing is not None else None

    def _on_finished(self, token_hash: str) -> None:
        self._sessions.pop(token_hash, None)

    async def shutdown(self) -> None:
        """Graceful-shutdown path (plan §9) — tells every still-active
        session's client plainly rather than silently orphaning its
        process tree on a rolling deploy."""
        for runtime, _start_task in list(self._sessions.values()):
            try:
                await runtime.force_stop_for_shutdown()
            except Exception:  # pragma: no cover - best-effort during shutdown
                logger.exception("error force-stopping a recording session during shutdown")
