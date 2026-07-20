# Build context is the repo root (uv workspace member; also needs Chromium
# for Playwright-driven crawling).
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY . .

RUN uv sync --frozen --no-dev --package discovery-worker
RUN /app/.venv/bin/playwright install --with-deps chromium

# Invoke the venv directly — `uv run` re-syncs (and would pull dev deps
# back in) on every container start; see apps/api/Dockerfile for why.
CMD ["/app/.venv/bin/python", "-m", "discovery_worker.worker"]
