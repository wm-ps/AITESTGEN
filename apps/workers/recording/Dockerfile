# Build context is the repo root (uv workspace member; also needs a real
# headed Chromium under a virtual display, not just Playwright's usual
# headless one — the Playwright Inspector window Codegen opens is a
# separate native window, never reachable via a page-level CDP screencast;
# see the Record and Play plan). First Dockerfile in this repo to install
# display-server packages — no other worker here runs anything headed.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# xvfb: the virtual display Codegen's browser + Inspector windows render
# onto. x11vnc: the raw VNC (RFB) server this app's own /vnc websocket
# route proxies to directly (no separate websockify process — see
# recording_worker/display.py's own docstring for why). nodejs/npm: the
# typecheck gate (packages/playwright_typecheck/typecheck — real
# @playwright/test types to catch hallucinated-matcher/undefined-var bugs in
# Codegen's own recorded output before persisting it) shells out to a real
# `node`, same as generation-worker's own Dockerfile already installs Node
# for, for the identical gate. xdotool: there's no window manager running
# under Xvfb, so nothing else arbitrates window placement — window_layout.py
# uses it to explicitly, deterministically position the target-app browser
# window so it never overlaps Codegen's own Inspector window (which
# Playwright itself hardcodes to a fixed position/size).
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    nodejs \
    npm \
    xdotool \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_LINK_MODE=copy

# Heavy, rarely-changing layers first (third-party deps, Chromium, npm) so
# dev-start's rebuild on every launch only redoes the cheap source COPY +
# workspace install below. Previously `COPY . .` came first, so any source
# edit re-ran all of these (~5 min per start).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --package recording-worker --no-install-workspace
RUN /app/.venv/bin/playwright install --with-deps chromium
COPY packages/playwright_typecheck/typecheck/package.json packages/playwright_typecheck/typecheck/package-lock.json packages/playwright_typecheck/typecheck/
RUN cd packages/playwright_typecheck/typecheck && npm install

# node_modules/.venv are .dockerignore'd, so this COPY doesn't clobber them.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package recording-worker

EXPOSE 8100
CMD ["/app/.venv/bin/uvicorn", "recording_worker.app:app", "--host", "0.0.0.0", "--port", "8100"]
