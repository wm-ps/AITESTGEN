"""Spawning the real `playwright codegen` CLI (plan round 1: the actual
recording engine — never a custom action-capture reimplementation, never an
LLM) against a session's own Xvfb display, and reading back whatever it
wrote once stopped.

Uses the Python `playwright` package's own bundled CLI (`python -m
playwright codegen`) rather than shelling out to `npx playwright` — this
app already depends on `playwright>=1.57` (only, otherwise, for
`auth_mode.py`'s pre-authentication step) and every sibling worker already
invokes Playwright's CLI this same way (see `apps/workers/generation`'s
typecheck subprocess), so no Node runtime is added to this container purely
for Codegen.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path

from recording_worker.config import STOP_GRACE_SECONDS
from recording_worker.window_layout import layout_recording_windows


class CodegenStartError(Exception):
    """Codegen's `python -m playwright codegen` process failed to start."""


class CodegenSession:
    def __init__(
        self,
        *,
        target_url: str,
        display_env: str,
        process_group: int,
        output_path: Path,
        storage_state_path: Path | None,
    ) -> None:
        self._target_url = target_url
        self._display_env = display_env
        self._process_group = process_group
        self._output_path = output_path
        self._storage_state_path = storage_state_path
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        args = [
            "-m",
            "playwright",
            "codegen",
            "--target",
            "javascript",
            "--output",
            str(self._output_path),
        ]
        if self._storage_state_path is not None:
            args += ["--load-storage", str(self._storage_state_path)]
        args.append(self._target_url)

        # uvloop's subprocess_exec has no `process_group=<existing pgid>`
        # equivalent — joining the display's process group (so `stop()`'s
        # single killpg reaches Codegen too) needs the pre-3.11
        # `preexec_fn` idiom instead: `setpgid(0, pgid)` in the child.
        process_group = self._process_group
        # sys.executable, not a bare "python": this process's own venv
        # (where `playwright` is actually installed) isn't necessarily on
        # PATH for a bare-name lookup — confirmed live in this container,
        # bare `python` resolves to the base image's system interpreter,
        # which doesn't have `playwright` and crashes on import. That
        # failure was silent (stdout/stderr both DEVNULL below) and nothing
        # checked survival afterward, so every recording session "started"
        # successfully while Codegen's actual browser never launched at all.
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable,
            *args,
            env={**os.environ, "DISPLAY": self._display_env},
            preexec_fn=lambda: os.setpgid(0, process_group),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Mirrors display.py's own immediate-crash check for Xvfb/x11vnc —
        # `has_exited` existed for this already but was never wired in,
        # which is exactly how the bare-"python" bug above went unnoticed.
        await asyncio.sleep(0.5)
        if self.has_exited:
            raise CodegenStartError(f"codegen exited immediately (code={self._proc.returncode})")

        # Fire-and-forget: positioning is cosmetic, not on the critical path
        # to a usable session — the human can start interacting with the
        # video as soon as it renders, while this finds and pins the
        # windows in the background (bounded internally, never raises).
        # self._proc.pid, not process_group: confirmed live that Chromium's
        # own process tree isn't a member of this session's process group
        # at all (only Xvfb/x11vnc/the two directly-spawned wrapper
        # processes are) — it's a *descendant* of this pid instead, via
        # Playwright's own Node driver (see window_layout.py's own docstring).
        asyncio.create_task(layout_recording_windows(self._display_env, self._proc.pid))

    @property
    def has_exited(self) -> bool:
        return self._proc is not None and self._proc.returncode is not None

    async def stop_and_read_output(self) -> str:
        """SIGTERM's Codegen specifically (not the whole session process
        group — that happens separately, after this) so it gets the chance
        to flush `--output`'s file on a clean exit; escalates to SIGKILL
        only after `STOP_GRACE_SECONDS` (plan §11). Returns whatever ended
        up on disk, including an empty string if Codegen never wrote
        anything (e.g. stopped before any action was recorded)."""
        assert self._proc is not None
        if self._proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=STOP_GRACE_SECONDS)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self._proc.kill()
                await self._proc.wait()

        if not self._output_path.exists():
            return ""
        return self._output_path.read_text(encoding="utf-8")
