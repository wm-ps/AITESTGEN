"""The recording service's own FastAPI app — the first app in this repo
with inbound network surface of its own (every other worker is a pure
Temporal poller). Two websocket routes per session (plan §1 — kept
strictly separate so `react-vnc`'s RFB client never sees a JSON frame):

    /recordings/{token}/vnc      RFB-over-websocket only, proxied straight
                                  to this session's local x11vnc port.
    /recordings/{token}/control  JSON only: browser -> {"type": "stop"};
                                  service -> status/saved/failed messages.

Every route re-validates the raw token (hash + expiry + status, plan §10)
on every single connect — a token is never trusted just because an earlier
connect on the *other* route already accepted it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from recording_worker.registry import RecordingServiceBusy, SessionRegistry
from recording_worker.tokens import InvalidRecordingToken, load_session_for_connect

logger = logging.getLogger(__name__)

app = FastAPI(title="Record and Play — recording service")
_registry = SessionRegistry()


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    # uvicorn's own SIGTERM handling already drives this ASGI "shutdown"
    # event on a rolling deploy — this hook is what gets every still-active
    # session's client told plainly (plan §9) before the process actually
    # exits, instead of every open websocket just dropping silently.
    await _registry.shutdown()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _proxy_vnc(websocket: WebSocket, vnc_port: int) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", vnc_port)

    async def pump_tcp_to_ws() -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                await websocket.send_bytes(data)
        except (WebSocketDisconnect, RuntimeError):
            pass

    async def pump_ws_to_tcp() -> None:
        try:
            while True:
                data = await websocket.receive_bytes()
                writer.write(data)
                await writer.drain()
        except WebSocketDisconnect:
            pass

    try:
        done, pending = await asyncio.wait(
            [asyncio.create_task(pump_tcp_to_ws()), asyncio.create_task(pump_ws_to_tcp())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


@app.websocket("/recordings/{token}/vnc")
async def recordings_vnc(websocket: WebSocket, token: str) -> None:
    try:
        recording_session = load_session_for_connect(token)
        runtime = await _registry.get_or_start(recording_session)
    except InvalidRecordingToken:
        await websocket.close(code=4401)
        return
    except RecordingServiceBusy:
        await websocket.close(code=4503)
        return

    await websocket.accept()
    await runtime.attach(channel="vnc", socket=websocket)
    try:
        await _proxy_vnc(websocket, runtime.vnc_port)
    finally:
        await runtime.detach(channel="vnc", socket=websocket)


@app.websocket("/recordings/{token}/control")
async def recordings_control(websocket: WebSocket, token: str) -> None:
    try:
        recording_session = load_session_for_connect(token)
        runtime = await _registry.get_or_start(recording_session)
    except InvalidRecordingToken:
        await websocket.close(code=4401)
        return
    except RecordingServiceBusy:
        await websocket.close(code=4503)
        return

    await websocket.accept()
    await runtime.attach(channel="control", socket=websocket)
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "stop":
                await runtime.request_stop()
    except WebSocketDisconnect:
        pass
    finally:
        await runtime.detach(channel="control", socket=websocket)
