# Build context is the repo root (uv workspace member). Unlike
# discovery/generation, this worker shells out to `npx playwright test`
# against each TestRun's assembled TypeScript project, so it needs a real
# Node runtime baked in, not just the Python `playwright` package.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN uv sync --frozen --no-dev --package execution-worker

# Self-healing (HealTestActivity) reuses the shared tsc-based typecheck
# gate (packages/playwright_typecheck/typecheck, extracted from
# generation-worker so apps/workers/recording can reuse it too) — install
# its node_modules here too, same as generation's own Dockerfile step.
RUN cd packages/playwright_typecheck/typecheck && npm install

# Pre-install @playwright/test + Chromium once at image-build time. Every
# TestRun's own assembled project still runs `npm ci` against its own
# package.json, but the browser binaries this installs land in the OS-level
# cache (~/.cache/ms-playwright) so a fresh TestRun's browser install is a
# cache hit, not a multi-hundred-MB download per run.
RUN npm install -g @playwright/test && npx playwright install --with-deps chromium

# Warm npm's cache with the Allure report packages every assembled project
# now lists (allure + allure-playwright, see test_suite_assembler's
# `_build_package_json` — keep these ranges in sync with it). Installed into
# a throwaway dir purely so their whole dependency tree lands in ~/.npm: on
# a cold cache the first TestRun's `npm install` downloads ~20 extra
# packages, which observed live pushed PrepareTestRunActivity past its
# 5-minute timeout.
RUN mkdir /tmp/allure-cache-warm && cd /tmp/allure-cache-warm \
    && npm install --no-save --no-audit --no-fund "@playwright/test@^1.48.0" "allure@^3.20.1" "allure-playwright@^3.13.0" \
    && cd / && rm -rf /tmp/allure-cache-warm

# Invoke the venv directly — `uv run` re-syncs (and would pull dev deps
# back in) on every container start; see apps/api/Dockerfile for why.
CMD ["/app/.venv/bin/python", "-m", "execution_worker.worker"]
