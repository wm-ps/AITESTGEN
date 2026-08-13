"""Checklist rule 3 — mandatory typecheck gate: `tsc --noEmit` against real
`@playwright/test` types catches undefined-variable/hallucinated-matcher bugs
in LLM-generated code at compile time, before it's ever persisted as a
TestAsset or run as a real test. Needs `npm install` run once in ../../typecheck
(installs typescript + @playwright/test so real types are checked against)."""

import asyncio
import os
import shutil
import uuid

_TYPECHECK_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "typecheck")
)
_TSC_JS = os.path.join(_TYPECHECK_DIR, "node_modules", "typescript", "bin", "tsc")


class TypecheckUnavailable(Exception):
    """node_modules for apps/workers/generation/typecheck isn't installed —
    run `npm install` there."""


async def typecheck_playwright_code(code: str) -> list[str]:
    """Returns tsc's error lines; an empty list means it type-checks clean.
    Invokes `node <typescript/bin/tsc>` directly rather than the npm-installed
    `tsc`/`tsc.cmd` shim — a real executable (`node`) runs identically on
    Windows/Linux, no shell needed either way."""
    if not os.path.exists(_TSC_JS):
        raise TypecheckUnavailable(f"{_TSC_JS} not found — run `npm install` in {_TYPECHECK_DIR}")

    # Unique per-call subdirectory (not a single fixed filename) so two
    # concurrent generation calls on the same worker process never typecheck
    # each other's files together — Node's module resolution still walks up
    # to the parent's node_modules from here.
    run_dir = os.path.join(_TYPECHECK_DIR, ".runs", uuid.uuid4().hex)
    os.makedirs(run_dir)
    spec_path = os.path.join(run_dir, "generated.spec.ts")
    try:
        with open(spec_path, "w", encoding="utf-8") as f:
            f.write(code)
        proc = await asyncio.create_subprocess_exec(
            "node",
            _TSC_JS,
            "--noEmit",
            "--skipLibCheck",
            "--target",
            "ES2022",
            "--module",
            "commonjs",
            "--moduleResolution",
            "node",
            "--esModuleInterop",
            spec_path,
            cwd=_TYPECHECK_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return []
        output = (stdout.decode(errors="replace") + stderr.decode(errors="replace")).strip()
        return output.splitlines() if output else [f"tsc exited {proc.returncode} with no output"]
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
