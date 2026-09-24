"""Re-export shim — the real implementation moved to `packages/playwright_typecheck`
so `apps/workers/recording` (Record and Play) can run the exact same tsc
gate on Codegen's own recorded output, without depending on the whole
generation worker for one function. Kept here, unchanged in shape, so
every existing call site/test in this worker needs no import changes."""

from playwright_typecheck import TypecheckUnavailable, typecheck_playwright_code

__all__ = ["TypecheckUnavailable", "typecheck_playwright_code"]
