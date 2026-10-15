"""SessionRuntime.request_cancel and its races with Stop and Save, the
registry's dead-session guards, and the control route's cancelled reply —
no real display, Codegen, or database (every collaborator is mocked)."""

import asyncio
import types
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from recording_worker import registry as registry_module
from recording_worker import runtime as runtime_module
from recording_worker.runtime import CANCELLED_CLOSE_CODE, RuntimeState, SessionRuntime
from recording_worker.tokens import InvalidRecordingToken, RecordingSessionCancelled


@pytest.fixture
def deps(monkeypatch):
    deps = types.SimpleNamespace(
        mark_cancelled=MagicMock(return_value=True),
        mark_complete=MagicMock(),
        mark_failed=MagicMock(),
        save=MagicMock(
            return_value=types.SimpleNamespace(
                journey_external_id=uuid.uuid4(),
                scenario_external_id=uuid.uuid4(),
                test_case_number=7,
            )
        ),
        typecheck=AsyncMock(return_value=[]),
        display=MagicMock(),
    )
    deps.display.stop = AsyncMock()
    monkeypatch.setattr(runtime_module, "mark_cancelled_sync", deps.mark_cancelled)
    monkeypatch.setattr(runtime_module, "mark_complete_sync", deps.mark_complete)
    monkeypatch.setattr(runtime_module, "mark_failed_sync", deps.mark_failed)
    monkeypatch.setattr(runtime_module, "save_recording_sync", deps.save)
    monkeypatch.setattr(runtime_module, "typecheck_playwright_code", deps.typecheck)
    monkeypatch.setattr(runtime_module, "uncomment_codegen_assertions", lambda code: code)
    monkeypatch.setattr(runtime_module, "normalize_recorded_spec", lambda code, **_: code)
    monkeypatch.setattr(runtime_module, "parse_steps", lambda code: [])
    monkeypatch.setattr(
        runtime_module, "load_application_sync", lambda _id: types.SimpleNamespace(id=uuid.uuid4())
    )
    monkeypatch.setattr(runtime_module, "NoVncDisplayBackend", lambda **_: deps.display)
    return deps


def _make_runtime(tmp_path, monkeypatch) -> tuple[SessionRuntime, types.SimpleNamespace]:
    monkeypatch.setattr(runtime_module, "SESSION_WORK_ROOT", str(tmp_path))
    allocator = MagicMock()
    on_finished = MagicMock()
    row = types.SimpleNamespace(
        id=uuid.uuid4(),
        external_id=uuid.uuid4(),
        token_hash="hash",
        application_id=uuid.uuid4(),
        auth_mode="logged_out",
        name="cancel test",
    )
    runtime = SessionRuntime(
        recording_session=row,
        allocator=allocator,
        resources=types.SimpleNamespace(display=3, vnc_port=5903),
        on_finished=on_finished,
    )
    codegen = MagicMock()
    codegen.terminate = AsyncMock()
    codegen.stop_and_read_output = AsyncMock(return_value="test('x', async () => {})")
    runtime._codegen = codegen
    runtime._discovery_run_id = uuid.uuid4()
    runtime.state = RuntimeState.RECORDING
    socket = MagicMock()
    socket.send_json = AsyncMock()
    socket.close = AsyncMock()
    runtime._control_sockets.add(socket)
    mocks = types.SimpleNamespace(
        allocator=allocator, on_finished=on_finished, codegen=codegen, socket=socket
    )
    return runtime, mocks


def _sent(socket) -> list[dict]:
    return [c.args[0] for c in socket.send_json.call_args_list]


@pytest.mark.asyncio
async def test_cancel_discards_and_tears_everything_down(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)

    await runtime.request_cancel()

    assert runtime.state == RuntimeState.CANCELLED
    assert runtime.is_finished
    deps.mark_cancelled.assert_called_once()
    assert {"type": "cancelled"} in _sent(m.socket)
    m.codegen.terminate.assert_awaited_once()
    m.codegen.stop_and_read_output.assert_not_called()
    deps.display.stop.assert_awaited_once()
    m.allocator.release.assert_called_once_with(3)
    m.on_finished.assert_called_once_with("hash")
    m.socket.close.assert_awaited_once_with(code=CANCELLED_CLOSE_CODE)
    deps.save.assert_not_called()
    deps.mark_complete.assert_not_called()
    deps.mark_failed.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_cancel_cleans_up_exactly_once(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)

    await asyncio.gather(runtime.request_cancel(), runtime.request_cancel())
    await runtime.request_cancel()

    deps.mark_cancelled.assert_called_once()
    m.allocator.release.assert_called_once()
    m.on_finished.assert_called_once()
    deps.display.stop.assert_awaited_once()
    assert _sent(m.socket).count({"type": "cancelled"}) == 1


@pytest.mark.asyncio
async def test_cancel_during_save_is_a_noop_and_the_save_wins(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)
    save_started = asyncio.Event()
    release_save = asyncio.Event()
    loop = asyncio.get_running_loop()

    def slow_save(**_):
        loop.call_soon_threadsafe(save_started.set)
        asyncio.run_coroutine_threadsafe(release_save.wait(), loop).result()
        return deps.save.return_value

    monkeypatch.setattr(runtime_module, "save_recording_sync", slow_save)

    stop_task = asyncio.create_task(runtime.request_stop())
    await save_started.wait()
    assert runtime.state == RuntimeState.SAVING
    cancel_task = asyncio.create_task(runtime.request_cancel())
    await asyncio.sleep(0.05)
    assert not cancel_task.done()  # blocked on the save's lock
    release_save.set()
    await asyncio.gather(stop_task, cancel_task)

    assert runtime.state == RuntimeState.COMPLETE
    deps.mark_complete.assert_called_once()
    deps.mark_cancelled.assert_not_called()
    m.allocator.release.assert_called_once()
    m.on_finished.assert_called_once()
    assert {"type": "cancelled"} not in _sent(m.socket)


@pytest.mark.asyncio
async def test_cancel_after_a_failed_save_stays_failed(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)
    deps.save.side_effect = RuntimeError("db down")

    await asyncio.gather(runtime.request_stop(), runtime.request_cancel())

    assert runtime.state == RuntimeState.FAILED
    deps.mark_failed.assert_called_once()
    deps.mark_cancelled.assert_not_called()
    m.allocator.release.assert_called_once()
    m.on_finished.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_after_a_typecheck_failure_stays_failed(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)
    deps.typecheck.return_value = ["TS2304: Cannot find name 'x'"]

    await runtime.request_stop()
    await runtime.request_cancel()

    assert runtime.state == RuntimeState.FAILED
    deps.mark_cancelled.assert_not_called()
    deps.save.assert_not_called()
    m.allocator.release.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_db_failure_keeps_recording_and_reports_it(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)
    deps.mark_cancelled.side_effect = RuntimeError("db down")

    await runtime.request_cancel()

    assert runtime.state == RuntimeState.RECORDING
    assert not runtime.is_finished
    sent = _sent(m.socket)
    assert any(msg["type"] == "cancel_failed" for msg in sent)
    assert {"type": "cancelled"} not in sent
    m.codegen.terminate.assert_not_called()
    deps.display.stop.assert_not_called()
    m.allocator.release.assert_not_called()
    m.on_finished.assert_not_called()

    deps.mark_cancelled.side_effect = None
    await runtime.request_cancel()

    assert runtime.state == RuntimeState.CANCELLED
    m.allocator.release.assert_called_once()
    m.on_finished.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_on_a_row_already_terminal_does_nothing(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)
    deps.mark_cancelled.return_value = False

    await runtime.request_cancel()

    assert runtime.state == RuntimeState.RECORDING
    assert m.socket.send_json.await_count == 0
    m.allocator.release.assert_not_called()
    m.on_finished.assert_not_called()


@pytest.mark.parametrize("failing", ["display", "codegen"])
@pytest.mark.asyncio
async def test_cleanup_continues_past_a_failing_step(deps, tmp_path, monkeypatch, failing):
    runtime, m = _make_runtime(tmp_path, monkeypatch)
    if failing == "display":
        deps.display.stop.side_effect = OSError("killpg failed")
    else:
        m.codegen.terminate.side_effect = OSError("no such process")
    m.allocator.release.side_effect = None

    await runtime.request_cancel()

    m.codegen.terminate.assert_awaited_once()
    deps.display.stop.assert_awaited_once()
    m.allocator.release.assert_called_once()
    m.on_finished.assert_called_once()
    m.socket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_finished_runs_even_if_release_fails(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)
    m.allocator.release.side_effect = RuntimeError("slot bookkeeping broke")

    await runtime.request_cancel()

    m.allocator.release.assert_called_once()
    m.on_finished.assert_called_once()


@pytest.mark.asyncio
async def test_attach_after_cleanup_is_refused(deps, tmp_path, monkeypatch):
    runtime, m = _make_runtime(tmp_path, monkeypatch)
    await runtime.request_cancel()
    late_socket = MagicMock()

    assert await runtime.attach(channel="control", socket=late_socket) is False
    assert late_socket not in runtime._control_sockets
    m.allocator.release.assert_called_once()


# -- registry ---------------------------------------------------------


def _row(token_hash: str = "hash"):
    return types.SimpleNamespace(id=uuid.uuid4(), external_id=uuid.uuid4(), token_hash=token_hash)


@pytest.mark.asyncio
async def test_registry_refuses_a_finished_runtime_still_registered(monkeypatch):
    registry = registry_module.SessionRegistry()
    dead = MagicMock(is_finished=True, state=RuntimeState.CANCELLED)
    done = asyncio.get_running_loop().create_future()
    done.set_result(None)
    registry._sessions["hash"] = (dead, done)

    with pytest.raises(RecordingSessionCancelled):
        await registry.get_or_start(_row())

    dead.state = RuntimeState.COMPLETE
    with pytest.raises(InvalidRecordingToken):
        await registry.get_or_start(_row())


@pytest.mark.parametrize(
    ("status", "error"),
    [("cancelled", RecordingSessionCancelled), ("complete", InvalidRecordingToken)],
)
@pytest.mark.asyncio
async def test_registry_never_relaunches_a_session_finished_in_the_db(monkeypatch, status, error):
    # The connect loaded the row while it was still live, then the cancel
    # committed and popped the registry entry before get_or_start ran.
    monkeypatch.setattr(registry_module, "load_status_sync", lambda _id: status)
    launched = MagicMock()
    monkeypatch.setattr(registry_module, "SessionRuntime", launched)
    registry = registry_module.SessionRegistry()
    registry._allocator = MagicMock()

    with pytest.raises(error):
        await registry.get_or_start(_row())

    launched.assert_not_called()
    registry._allocator.acquire.assert_not_called()


# -- control route ----------------------------------------------------


def test_control_connect_to_a_cancelled_session_says_so(monkeypatch):
    from recording_worker import app as app_module
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    def cancelled(_token):
        raise RecordingSessionCancelled("session was cancelled")

    monkeypatch.setattr(app_module, "load_session_for_connect", cancelled)

    with TestClient(app_module.app) as client:
        with client.websocket_connect("/recordings/sometoken/control") as ws:
            assert ws.receive_json() == {"type": "cancelled"}
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
    assert closed.value.code == CANCELLED_CLOSE_CODE
