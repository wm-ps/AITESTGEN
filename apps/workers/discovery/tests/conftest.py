"""Spins up the local test-target app (fixtures/target_app.py) on a real
socket for DiscoveryActivity's crawl-loop tests — Playwright needs a real
HTTP server, not an ASGI transport.
"""

import socket
import threading
import time

import pytest
import uvicorn
from fixtures.target_app import app, configure


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def target_app_url():
    configure(expire_after=None)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)

    yield f"http://127.0.0.1:{port}/"

    server.should_exit = True
    thread.join(timeout=5)
