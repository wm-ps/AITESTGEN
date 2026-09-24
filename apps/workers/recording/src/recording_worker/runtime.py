"""SessionRuntime — the per-recording-session state machine (plan §11):

    pending -> connecting -> recording -> disconnected -> recording (reconnect)
                                        -> abandoned (grace lapsed, cleanup)
             recording -> stopping -> saving -> complete | failed -> cleanup

Durable state (`RecordingSession.status` in Postgres) stays coarse —
pending/recording/complete/failed — while this class tracks the
finer-grained live states in memory and pushes them over the `control`
websocket channel; only this class's owning `SessionRegistry` needs to
know about a `SessionRuntime` at all.

Every resource a session touches (Xvfb display, ports, temp directory,
Codegen process) is owned exclusively by one `SessionRuntime` instance —
`SessionRegistry` is what makes that isolation load-bearing (plan round 2):
it never hands two sessions the same allocator slot at once.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import logging
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from domain import RecordingSession
from playwright_typecheck import typecheck_playwright_code
from starlette.websockets import WebSocket

from recording_worker.allocator import AllocatedResources, DisplayPortAllocator
from recording_worker.auth_mode import bootstrap_storage_state
from recording_worker.codegen_session import CodegenSession
from recording_worker.config import (
    MAX_RECORDING_SECONDS,
    RECONNECT_GRACE_SECONDS,
    SESSION_WORK_ROOT,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
)
from recording_worker.display import NoVncDisplayBackend
from recording_worker.persistence import (
    create_recording_discovery_run_sync,
    load_application_sync,
    save_recording_sync,
)
from recording_worker.steps_parser import parse_steps
from recording_worker.tokens import mark_complete_sync, mark_failed_sync, mark_first_connect_sync

logger = logging.getLogger(__name__)


class RuntimeState(enum.StrEnum):
    PENDING = "pending"
    CONNECTING = "connecting"
    RECORDING = "recording"
    DISCONNECTED = "disconnected"
    STOPPING = "stopping"
    SAVING = "saving"
    COMPLETE = "complete"
    FAILED = "failed"


class SessionRuntime:
    def __init__(
        self,
        *,
        recording_session: RecordingSession,
        allocator: DisplayPortAllocator,
        resources: AllocatedResources,
        on_finished: Callable[[str], None],
    ) -> None:
        self._row = recording_session
        self._allocator = allocator
        self._resources = resources
        self._on_finished = on_finished  # registry callback: remove this token_hash's entry

        self.state = RuntimeState.PENDING
        self._application = load_application_sync(recording_session.application_id)
        self._session_dir = Path(SESSION_WORK_ROOT) / str(recording_session.external_id)
        self._display = NoVncDisplayBackend(
            display=resources.display,
            vnc_port=resources.vnc_port,
            session_dir=self._session_dir,
            viewport=(VIEWPORT_WIDTH, VIEWPORT_HEIGHT),
        )
        self._codegen: CodegenSession | None = None
        self._storage_state_path: Path | None = None
        self._discovery_run_id: uuid.UUID | None = None

        self._control_sockets: set[WebSocket] = set()
        self._vnc_sockets: set[WebSocket] = set()
        self._grace_task: asyncio.Task | None = None
        self._max_duration_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._finished = False

    @property
    def vnc_port(self) -> int:
        return self._display.vnc_port

    @property
    def display_backend(self) -> NoVncDisplayBackend:
        return self._display

    # -- lifecycle -----------------------------------------------------

    async def start(self) -> None:
        self.state = RuntimeState.CONNECTING
        await asyncio.to_thread(mark_first_connect_sync, self._row.id)
        self._discovery_run_id = await asyncio.to_thread(
            create_recording_discovery_run_sync, self._application.id
        )

        await self._display.start()

        try:
            if self._row.auth_mode == "authenticated":
                self._storage_state_path = await bootstrap_storage_state(self._application)

            self._codegen = CodegenSession(
                target_url=self._application.url,
                display_env=self._display.display_env,
                process_group=self._display.join_process_group(),
                output_path=self._session_dir / "session.spec.ts",
                storage_state_path=self._storage_state_path,
            )
            await self._codegen.start()
        except BaseException:
            # The display already came up — a failure past this point (auth
            # bootstrap, Codegen itself) must not leak its Xvfb/x11vnc
            # process pair the same way an in-display failure would
            # (display.py's own `start()` already guards that case).
            with contextlib.suppress(Exception):
                await self._display.stop()
            raise

        self.state = RuntimeState.RECORDING
        self._max_duration_task = asyncio.create_task(self._max_duration_watchdog())
        await self._broadcast_control({"type": "status", "state": self.state.value})

    async def attach(self, *, channel: str, socket: WebSocket) -> None:
        if channel == "control":
            self._control_sockets.add(socket)
        else:
            self._vnc_sockets.add(socket)
        if self.state == RuntimeState.DISCONNECTED:
            self._cancel_grace_timer()
            self.state = RuntimeState.RECORDING
            await self._broadcast_control({"type": "status", "state": self.state.value})

    async def detach(self, *, channel: str, socket: WebSocket) -> None:
        if channel == "control":
            self._control_sockets.discard(socket)
        else:
            self._vnc_sockets.discard(socket)
        if self._control_sockets or self._vnc_sockets:
            return
        if self.state in (RuntimeState.RECORDING,):
            self.state = RuntimeState.DISCONNECTED
            self._grace_task = asyncio.create_task(self._grace_timeout())

    async def _grace_timeout(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(RECONNECT_GRACE_SECONDS)
            if self.state == RuntimeState.DISCONNECTED:
                await self._finish(
                    status="failed",
                    error_message="abandoned: no reconnect within grace period",
                )

    def _cancel_grace_timer(self) -> None:
        if self._grace_task is not None:
            self._grace_task.cancel()
            self._grace_task = None

    async def _max_duration_watchdog(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(MAX_RECORDING_SECONDS)
            if self.state in (RuntimeState.RECORDING, RuntimeState.DISCONNECTED):
                await self.request_stop()

    async def request_stop(self) -> None:
        """The only trigger for the save flow — an explicit `{"type":
        "stop"}` on `control`, or the max-duration watchdog above. Never
        called for a mere disconnect (plan §3)."""
        async with self._lock:
            if self.state in (RuntimeState.STOPPING, RuntimeState.SAVING) or self._finished:
                return
            self._cancel_grace_timer()
            self.state = RuntimeState.STOPPING
            await self._broadcast_control({"type": "status", "state": self.state.value})

            assert self._codegen is not None
            code = await self._codegen.stop_and_read_output()

            self.state = RuntimeState.SAVING
            await self._broadcast_control({"type": "status", "state": self.state.value})

            if not code.strip():
                await self._finish(
                    status="failed", error_message="no actions were recorded before Stop and Save"
                )
                return

            typecheck_errors = await typecheck_playwright_code(code)
            if typecheck_errors:
                await self._finish(status="failed", error_message="; ".join(typecheck_errors))
                return

            requires_auth = self._row.auth_mode == "authenticated"
            steps = parse_steps(code)
            assert self._discovery_run_id is not None
            try:
                saved = await asyncio.to_thread(
                    save_recording_sync,
                    application_id=self._application.id,
                    discovery_run_id=self._discovery_run_id,
                    code=code,
                    steps=steps,
                    requires_auth=requires_auth,
                )
            except Exception as exc:  # pragma: no cover - defensive, mirrors save-path errors
                logger.exception("recording session %s: failed to persist", self._row.external_id)
                await self._finish(status="failed", error_message=str(exc))
                return

            await asyncio.to_thread(
                mark_complete_sync,
                self._row.id,
                journey_external_id=saved.journey_external_id,
                scenario_external_id=saved.scenario_external_id,
            )
            self.state = RuntimeState.COMPLETE
            await self._broadcast_control(
                {
                    "type": "saved",
                    "journey_external_id": str(saved.journey_external_id),
                    "scenario_external_id": str(saved.scenario_external_id),
                    "test_case_number": saved.test_case_number,
                }
            )
            await self._cleanup()

    async def force_stop_for_shutdown(self) -> None:
        """Graceful-shutdown path (plan §9) — a rolling deploy's SIGTERM to
        this whole service, not a per-session Stop. Never attempts to save
        whatever was mid-recording; tells the client plainly instead."""
        await self._broadcast_control({"type": "failed", "error": "server restarting"})
        await self._finish(status="failed", error_message="server restarted during recording")

    async def _finish(self, *, status: str, error_message: str) -> None:
        if self._finished:
            return
        await asyncio.to_thread(mark_failed_sync, self._row.id, error_message=error_message)
        self.state = RuntimeState.FAILED
        await self._broadcast_control({"type": "failed", "error": error_message})
        await self._cleanup()

    async def _cleanup(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._cancel_grace_timer()
        if self._max_duration_task is not None:
            self._max_duration_task.cancel()
        with contextlib.suppress(Exception):
            await self._display.stop()
        if self._storage_state_path is not None:
            self._storage_state_path.unlink(missing_ok=True)
        shutil.rmtree(self._session_dir, ignore_errors=True)
        self._allocator.release(self._resources.display)
        for socket in [*self._control_sockets, *self._vnc_sockets]:
            with contextlib.suppress(Exception):
                await socket.close()
        self._on_finished(self._row.token_hash)

    async def _broadcast_control(self, message: dict) -> None:
        for socket in list(self._control_sockets):
            with contextlib.suppress(Exception):
                await socket.send_json(message)
