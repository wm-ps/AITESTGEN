"""Self-healing's assertion guard: whatever a heal fixes, it may never
change, add or remove an `expect(...)` assertion. `assertion_changes` compares every
assertion of the spec before and after a heal — subject (including its
locator), matcher, `.not`/`.soft`, expected arguments, options, and whether
it is awaited — and reports each one the heal changed, added or removed.

The parsing is TypeScript's own (`../../typecheck/assertions.js`, run with
the same `typescript` install and `node` launch as `typecheck.py`), not a
regex, so formatting, comments and quote style never count as a change."""

import difflib
import json
import os

from playwright_typecheck.process_tree import run_process
from playwright_typecheck.typecheck import _TYPECHECK_DIR, TypecheckUnavailable

_ASSERTIONS_JS = os.path.join(_TYPECHECK_DIR, "assertions.js")
_TYPESCRIPT_DIR = os.path.join(_TYPECHECK_DIR, "node_modules", "typescript")
_MAX_SHOWN = 240


class AssertionGuardError(Exception):
    """assertions.js itself failed — the guard couldn't run."""


def _short(fingerprint: str) -> str:
    return fingerprint if len(fingerprint) <= _MAX_SHOWN else fingerprint[: _MAX_SHOWN - 1] + "…"


async def assertion_fingerprints(old_code: str, new_code: str) -> tuple[list[str], list[str]]:
    if not os.path.exists(_TYPESCRIPT_DIR):
        raise TypecheckUnavailable(
            f"{_TYPESCRIPT_DIR} not found — run `npm install` in {_TYPECHECK_DIR}"
        )
    returncode, stdout, stderr = await run_process(
        "node",
        _ASSERTIONS_JS,
        cwd=_TYPECHECK_DIR,
        input=json.dumps({"old": old_code, "new": new_code}).encode("utf-8"),
    )
    if returncode != 0:
        raise AssertionGuardError(
            f"assertions.js exited {returncode}: {stderr.decode(errors='replace').strip()[:500]}"
        )
    result = json.loads(stdout.decode("utf-8"))
    return result["old"], result["new"]


async def assertion_changes(old_code: str, new_code: str) -> list[str]:
    """Empty when every assertion in `new_code` is exactly as it was in
    `old_code`, in the same order; otherwise one readable line per change.
    There is no exception for locators inside assertions."""
    old, new = await assertion_fingerprints(old_code, new_code)
    changes: list[str] = []
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            for offset in range(max(i2 - i1, j2 - j1)):
                before = old[i1 + offset] if i1 + offset < i2 else None
                after = new[j1 + offset] if j1 + offset < j2 else None
                if before is not None and after is not None:
                    changes.append(
                        f"assertion {i1 + offset + 1} changed: {_short(before)} → {_short(after)}"
                    )
                elif before is not None:
                    changes.append(f"assertion removed: {_short(before)}")
                else:
                    changes.append(f"assertion added: {_short(after)}")  # type: ignore[arg-type]
        elif tag == "delete":
            changes.extend(f"assertion removed: {_short(fp)}" for fp in old[i1:i2])
        elif tag == "insert":
            changes.extend(f"assertion added: {_short(fp)}" for fp in new[j1:j2])
    return changes
