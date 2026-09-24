# Build context is the repo root (uv workspace member).
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Node is needed for the typecheck gate (packages/playwright_typecheck/typecheck —
# real @playwright/test types to catch hallucinated-matcher/undefined-var bugs
# in generated specs before they're persisted) and, separately, to spawn
# @playwright/mcp for live-exploration (generation_worker/live_exploration/).
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN uv sync --frozen --no-dev --package generation-worker
# Lives in packages/playwright_typecheck now (Record and Play extracted it
# into a shared package so apps/workers/recording can reuse the same gate
# on Codegen's own output) — generation_worker.typecheck is just a
# re-export shim over it.
RUN cd packages/playwright_typecheck/typecheck && npm install

# auth_bootstrap.py launches a real (Python) Chromium briefly to produce an
# authenticated storage_state for the live-exploration session.
RUN /app/.venv/bin/playwright install --with-deps chromium

# Pre-fetch @playwright/mcp (and its own, Node-side Chromium — separate from
# the Python one installed above) at build time — same version pinned in
# generation_worker/live_exploration/mcp_client.py's _PLAYWRIGHT_MCP_PACKAGE,
# keep both in sync on a version bump. Live-exploration activities spawn this
# as a subprocess per session; caching it now means no npm network call (or
# version drift, or a slow first request) at request time.
RUN npx --yes @playwright/mcp@0.0.41 --version \
    && npx --yes playwright@1.57.0 install --with-deps chromium

# Invoke the venv directly — `uv run` re-syncs (and would pull dev deps
# back in) on every container start; see apps/api/Dockerfile for why.
CMD ["/app/.venv/bin/python", "-m", "generation_worker.worker"]
