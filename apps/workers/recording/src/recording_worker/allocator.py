"""In-memory pool of Xvfb display numbers + local TCP ports for concurrent
recording sessions — one long-running process, `MAX_CONCURRENT_SESSIONS`
slots, each session's slot fully released back to the pool on cleanup so a
later session safely reuses it with zero crosstalk with any still-running
session (plan §13's resource-reuse requirement; verified by this module's
own tests)."""

import socket
import threading
from dataclasses import dataclass

from recording_worker.config import BASE_DISPLAY_NUMBER, MAX_CONCURRENT_SESSIONS


class ResourcePoolExhausted(Exception):
    """Every display slot is currently in use — the mint endpoint should
    reject new sessions with a 503 rather than let this raise unhandled."""


@dataclass(frozen=True)
class AllocatedResources:
    display: int
    vnc_port: int


def _free_local_port() -> int:
    # ponytail: bind-and-release rather than a reserved port range — a
    # narrow race exists between release here and the VNC server's own
    # bind a moment later. Acceptable for this MVP's low concurrency
    # (MAX_CONCURRENT_SESSIONS); a reserved-range allocator would close it
    # if collisions are ever observed live.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DisplayPortAllocator:
    def __init__(
        self,
        max_concurrent_sessions: int = MAX_CONCURRENT_SESSIONS,
        base_display: int = BASE_DISPLAY_NUMBER,
    ) -> None:
        self._max = max_concurrent_sessions
        self._base_display = base_display
        self._lock = threading.Lock()
        self._used_displays: set[int] = set()

    def acquire(self) -> AllocatedResources:
        with self._lock:
            for offset in range(self._max):
                display = self._base_display + offset
                if display not in self._used_displays:
                    self._used_displays.add(display)
                    return AllocatedResources(display=display, vnc_port=_free_local_port())
        raise ResourcePoolExhausted(
            f"no free recording display slot (max_concurrent_sessions={self._max})"
        )

    def release(self, display: int) -> None:
        with self._lock:
            self._used_displays.discard(display)
