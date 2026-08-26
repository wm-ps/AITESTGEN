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

# Self-healing (HealTestActivity) reuses generation-worker's tsc-based
# typecheck gate (apps/workers/generation/typecheck) — install its
# node_modules here too, same as generation's own Dockerfile step.
RUN cd apps/workers/generation/typecheck && npm install

# Pre-install @playwright/test + Chromium once at image-build time. Every
# TestRun's own assembled project still runs `npm ci` against its own
# package.json, but the browser binaries this installs land in the OS-level
# cache (~/.cache/ms-playwright) so a fresh TestRun's browser install is a
# cache hit, not a multi-hundred-MB download per run.
RUN npm install -g @playwright/test && npx playwright install --with-deps chromium

# Invoke the venv directly — `uv run` re-syncs (and would pull dev deps
# back in) on every container start; see apps/api/Dockerfile for why.
CMD ["/app/.venv/bin/python", "-m", "execution_worker.worker"]
