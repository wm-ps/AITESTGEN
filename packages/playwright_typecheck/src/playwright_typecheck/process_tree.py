"""Subprocesses that can be killed as a whole tree, plus a kill scope that
kills every one still running when the work it covers is cancelled.

`npx playwright test` (and `npm`/`npx` generally, `.cmd` shims on Windows)
starts node, which starts the browsers — killing only the direct child
leaves the rest running. Each process here starts in its own process group
/ session, so the whole tree can be killed at once: `taskkill /T` on
Windows, `killpg` elsewhere.

`kill_scope()` registers every process started inside it. It's a
contextvar, so sync code run through `asyncio.to_thread` (which copies the
context) registers into the same scope; `KillScope.cancel()` kills them all
and makes any later spawn in the scope raise `RunCancelled` instead.

Lives in playwright_typecheck because its own tsc / assertions.js runs need
it and both the generation and execution workers already depend on this
package.
"""

import asyncio
import contextlib
import contextvars
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator

_IS_WINDOWS = sys.platform == "win32"
_TERM_GRACE_SECONDS = 3.0


# Child processes run AI-written code that untrusted page text can steer, so
# they never inherit the worker's own environment (Vault token, DB URL, cloud
# and LLM keys...) — only what node/npm/Playwright need to start.
_ENV_ALLOWED = frozenset(
    {
        "PATH", "HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP", "TZ", "LANG", "LANGUAGE", "CI",
        # Windows (local dev) needs these for node/npm/Chromium to start.
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "APPDATA", "LOCALAPPDATA",
        "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA",
    }
)  # fmt: skip
_ENV_ALLOWED_PREFIXES = ("LC_", "NODE_", "NPM_CONFIG_", "PLAYWRIGHT_")


def safe_env() -> dict[str, str]:
    """The worker's environment filtered down to what a child process needs.
    What every process here gets unless the caller passes its own."""
    return {
        key: value
        for key, value in os.environ.items()
        if key.upper() in _ENV_ALLOWED or key.upper().startswith(_ENV_ALLOWED_PREFIXES)
    }


class RunCancelled(Exception):
    """The kill scope was cancelled — a process was refused or killed."""


def _new_group_kwargs() -> dict:
    if _IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def kill_tree(pid: int) -> None:
    """Kills `pid` and every descendant. Best-effort, never raises."""
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=15
            )
            return
        # start_new_session made pid its own process group id.
        os.killpg(pid, signal.SIGTERM)
        deadline = time.monotonic() + _TERM_GRACE_SECONDS
        while time.monotonic() < deadline:
            os.killpg(pid, 0)  # raises ProcessLookupError once the group is gone
            time.sleep(0.1)
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError, subprocess.SubprocessError):
        pass


class KillScope:
    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self._pids: set[int] = set()
        self._lock = threading.Lock()

    def _track(self, pid: int) -> None:
        with self._lock:
            self._pids.add(pid)
        # Cancelled between the caller's check and this spawn: kill it now.
        if self.cancelled.is_set():
            kill_tree(pid)

    def _untrack(self, pid: int) -> None:
        with self._lock:
            self._pids.discard(pid)

    def cancel(self) -> None:
        """Kill every tracked process tree and refuse new ones. Blocking
        (taskkill / the SIGTERM grace) — call it via `asyncio.to_thread`
        from async code."""
        self.cancelled.set()
        with self._lock:
            pids = list(self._pids)
        for pid in pids:
            kill_tree(pid)


_current_scope: contextvars.ContextVar[KillScope | None] = contextvars.ContextVar(
    "playwright_typecheck_kill_scope", default=None
)


@contextlib.contextmanager
def kill_scope() -> Iterator[KillScope]:
    scope = KillScope()
    token = _current_scope.set(scope)
    try:
        yield scope
    finally:
        _current_scope.reset(token)


def _check_not_cancelled(scope: KillScope | None) -> None:
    if scope is not None and scope.cancelled.is_set():
        raise RunCancelled("cancelled before the process started")


async def run_process(
    *args: str,
    cwd: str,
    env: dict | None = None,
    input: bytes | None = None,
    timeout: float | None = None,
) -> tuple[int, bytes, bytes]:
    """(returncode, stdout, stderr). On timeout or task cancellation the
    whole tree is killed before `TimeoutError`/`CancelledError` propagates;
    killed by its kill scope instead, it raises `RunCancelled`."""
    scope = _current_scope.get()
    _check_not_cancelled(scope)
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=safe_env() if env is None else env,
        stdin=asyncio.subprocess.PIPE if input is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **_new_group_kwargs(),
    )
    if scope is not None:
        scope._track(proc.pid)
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(input), timeout=timeout)
    except BaseException:
        # Timeout or cancel: the tree must be gone before this returns, so a
        # caller that next deletes the project dir never races a live run.
        await asyncio.shield(asyncio.to_thread(kill_tree, proc.pid))
        with contextlib.suppress(BaseException):
            await asyncio.shield(proc.wait())
        raise
    finally:
        if scope is not None:
            scope._untrack(proc.pid)
    if scope is not None and scope.cancelled.is_set():
        raise RunCancelled("process killed by cancellation")
    return proc.returncode or 0, stdout, stderr


def run_process_sync(
    args: list[str],
    *,
    cwd: str,
    env: dict | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """`subprocess.run(..., check=True, capture_output=True)` whose whole
    tree is killed on timeout or when the enclosing kill scope is cancelled
    (then `RunCancelled` is raised instead of a result)."""
    scope = _current_scope.get()
    _check_not_cancelled(scope)
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=safe_env() if env is None else env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_new_group_kwargs(),
    )
    if scope is not None:
        scope._track(proc.pid)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        proc.communicate()
        raise
    finally:
        if scope is not None:
            scope._untrack(proc.pid)
    if scope is not None and scope.cancelled.is_set():
        raise RunCancelled("process killed by cancellation")
    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, args, stdout, stderr)
    return subprocess.CompletedProcess(args, proc.returncode, stdout, stderr)
