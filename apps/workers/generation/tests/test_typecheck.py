"""typecheck's sandbox must mirror the real exported spec's two-level depth
(tests/<suite>/<name>.spec.ts) or every generated spec that imports the
shared '../../support/auth' helper fails typecheck regardless of whether the
generated code is actually correct — see typecheck.py's run_root comment."""

import pytest

from generation_worker.typecheck import TypecheckUnavailable, typecheck_playwright_code

pytestmark = pytest.mark.asyncio


async def test_resolves_shared_support_auth_import() -> None:
    code = (
        "import { test } from '@playwright/test'\n"
        "import { fillCredentials } from '../../support/auth'\n\n"
        "test('x', async ({ page }) => {\n"
        "  await fillCredentials(page)\n"
        "})\n"
    )
    try:
        errors = await typecheck_playwright_code(code)
    except TypecheckUnavailable:
        pytest.skip("typecheck/node_modules not installed")
    assert errors == []
