"""Deterministically tag the first `test(...)` call with `{ tag: '@auth' }`/
`{ tag: '@public' }` so the exported project's Playwright config (which
filters projects by this tag) always agrees with `requires_auth`.

Duplicated from `generation_worker.spec_linter.apply_auth_tag` rather than
imported — that worker's dependency tree (langgraph, mcp, ai_provider, the
Playwright-MCP subprocess plumbing) is heavy, entirely unrelated to this
~20-line regex transform, and not worth pulling into this app for it; same
"different caller, not worth the coupling" call that module's own docstring
already makes for its own login-page-heuristic duplication.
"""

import re

_TEST_CALL_RE = re.compile(r"(test(?:\.describe)?)\(\s*(['\"])(.*?)\2\s*,\s*(?:\{[^}]*?\}\s*,\s*)?")
_INLINE_TAG_RE = re.compile(r"\s*@(?:auth|public)\b")


def apply_auth_tag(code: str, requires_auth: bool) -> str:
    tag = "@auth" if requires_auth else "@public"
    match = _TEST_CALL_RE.search(code)
    if match is None:
        return code
    call, quote, name = match.group(1), match.group(2), match.group(3)
    name = _INLINE_TAG_RE.sub("", name).strip()
    replacement = f"{call}({quote}{name}{quote}, {{ tag: '{tag}' }}, "
    return code[: match.start()] + replacement + code[match.end() :]
