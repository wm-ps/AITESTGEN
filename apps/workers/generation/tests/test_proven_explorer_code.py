"""Explorer scenarios carry a proven, house-style test (`grounding.proven_code`)
that Generate tests uses as-is when it compiles, instead of an AI rewrite."""

import asyncio
from types import SimpleNamespace

from generation_worker import activities


def _run(grounding: dict | None, errors: list[str]) -> str | None:
    async def fake_typecheck(code: str) -> list[str]:
        return errors

    original = activities.typecheck_playwright_code
    activities.typecheck_playwright_code = fake_typecheck
    try:
        return asyncio.run(
            activities._proven_explorer_code(SimpleNamespace(grounding=grounding), "scenario-1")
        )
    finally:
        activities.typecheck_playwright_code = original


def test_proven_code_is_used_when_it_compiles():
    code = "import { test } from '@playwright/test';\ntest('x', async ({ page }) => {});\n"
    assert _run({"proven_code": code}, []) == code


def test_falls_back_to_generation_when_it_does_not_compile():
    assert _run({"proven_code": "test("}, ["TS1005: ')' expected."]) is None


def test_ordinary_scenarios_are_generated():
    assert _run({"captured_flow": []}, []) is None
    assert _run(None, []) is None
