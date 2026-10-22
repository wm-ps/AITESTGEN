"""`process_tree` — a cancel or timeout must take down the whole tree (npx →
node → browsers), not just the direct child. Real processes: a parent that
starts a long-sleeping grandchild and records its pid."""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright_typecheck.process_tree import (
    RunCancelled,
    kill_scope,
    run_process,
    run_process_sync,
)

_PARENT = """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(sys.argv[1], "w").write(str(child.pid))
time.sleep(120)
"""


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
        ).stdout
        return str(pid) in out
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_for_pid_file(path: Path) -> int:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return int(path.read_text())
        time.sleep(0.1)
    raise AssertionError("parent never started its child")


def _wait_until_dead(pid: int) -> bool:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.2)
    return False


def test_cancelling_the_scope_kills_an_async_process_and_its_grandchild(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"

    async def _main() -> tuple[BaseException | None, int]:
        with kill_scope() as scope:
            run = asyncio.create_task(
                run_process(sys.executable, "-c", _PARENT, str(pid_file), cwd=str(tmp_path))
            )
            grandchild = await asyncio.to_thread(_wait_for_pid_file, pid_file)
            await asyncio.to_thread(scope.cancel)
            try:
                await run
            except BaseException as err:  # noqa: BLE001
                return err, grandchild
            return None, grandchild

    raised, grandchild = asyncio.run(_main())

    assert isinstance(raised, RunCancelled)
    assert _wait_until_dead(grandchild), "grandchild survived the kill"


def test_task_cancellation_kills_the_tree_before_propagating(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"

    async def _main() -> int:
        run = asyncio.create_task(
            run_process(sys.executable, "-c", _PARENT, str(pid_file), cwd=str(tmp_path))
        )
        grandchild = await asyncio.to_thread(_wait_for_pid_file, pid_file)
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run
        return grandchild

    grandchild = asyncio.run(_main())

    assert _wait_until_dead(grandchild)


def test_sync_process_in_a_thread_is_killed_by_its_scope(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"

    async def _main() -> tuple[BaseException | None, int]:
        with kill_scope() as scope:
            thread = asyncio.create_task(
                asyncio.to_thread(
                    run_process_sync,
                    [sys.executable, "-c", _PARENT, str(pid_file)],
                    cwd=str(tmp_path),
                )
            )
            grandchild = await asyncio.to_thread(_wait_for_pid_file, pid_file)
            await asyncio.to_thread(scope.cancel)
            try:
                await thread
            except BaseException as err:  # noqa: BLE001
                return err, grandchild
            return None, grandchild

    raised, grandchild = asyncio.run(_main())

    assert isinstance(raised, RunCancelled)
    assert _wait_until_dead(grandchild)


def test_a_cancelled_scope_refuses_new_processes(tmp_path: Path) -> None:
    with kill_scope() as scope:
        scope.cancel()
        with pytest.raises(RunCancelled):
            run_process_sync([sys.executable, "-c", "pass"], cwd=str(tmp_path))


def test_timeout_kills_the_tree(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"

    async def _main() -> None:
        await run_process(sys.executable, "-c", _PARENT, str(pid_file), cwd=str(tmp_path), timeout=3)

    with pytest.raises(TimeoutError):
        asyncio.run(_main())

    assert _wait_until_dead(_wait_for_pid_file(pid_file))
