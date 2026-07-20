# Build context is the repo root — this is a uv workspace member, and uv
# needs every workspace member's pyproject.toml present to resolve the shared
# uv.lock, even though only `api` and its path deps actually get installed.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY . .

RUN uv sync --frozen --no-dev --package api

# Invoke the venv directly rather than `uv run` — `uv run` re-syncs on every
# invocation, which at container startup means re-resolving/downloading
# (including dev deps, since --no-dev only applied to the build-time sync)
# on every restart, with no guarantee of network access at runtime.
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
