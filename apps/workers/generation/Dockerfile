# Build context is the repo root (uv workspace member).
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Node is needed only for the typecheck gate (apps/workers/generation/typecheck)
# — real @playwright/test types to catch hallucinated-matcher/undefined-var
# bugs in generated specs before they're persisted.
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN uv sync --frozen --no-dev --package generation-worker
RUN cd apps/workers/generation/typecheck && npm install

# Invoke the venv directly — `uv run` re-syncs (and would pull dev deps
# back in) on every container start; see apps/api/Dockerfile for why.
CMD ["/app/.venv/bin/python", "-m", "generation_worker.worker"]
