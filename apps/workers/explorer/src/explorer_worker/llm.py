"""Explorer's own GPT-5.6 client (OpenAI-compatible chat completions, reached
through the company LiteLLM gateway). Deliberately not `ai_provider` —
Explorer is standalone (docs/vantage-explorer/PLAN.md).

Two tiers: THINKING_MODEL (reasoning, used for understanding screens and
writing the App Summary) and FAST_MODEL (quick choices like "where next").
"""

import asyncio
import base64
import json
import logging
import os
import time
from typing import Any

import httpx

LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "").rstrip("/")
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
THINKING_MODEL = os.environ.get("EXPLORER_THINKING_MODEL", "gpt-5.6-sol")
FAST_MODEL = os.environ.get("EXPLORER_FAST_MODEL", "gpt-5.6-luna")

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


async def ask_json(
    system: str,
    user: str,
    *,
    images: list[bytes] | None = None,
    model: str = THINKING_MODEL,
    attempts: int = 3,
) -> dict[str, Any]:
    """One chat call that must come back as a JSON object."""
    if not LITELLM_BASE_URL:
        raise LLMError("LITELLM_BASE_URL is not set — start the worker with --env-file .env")
    content: list[dict[str, Any]] = [{"type": "text", "text": user}]
    for image in images or []:
        b64 = base64.b64encode(image).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
    }
    last: Exception | None = None
    # Debug trail in the worker log: what each call asks for, and the gist of
    # what came back, so a run can be followed without the database.
    logger.info(
        "model call -> %s%s: %s",
        model,
        f" (+{len(images)} image{'s' if len(images) > 1 else ''})" if images else "",
        _gist(user, 240),
    )
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=240) as client:
        for attempt in range(attempts):
            try:
                response = await client.post(
                    f"{LITELLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {LITELLM_API_KEY}"},
                    json=body,
                )
                response.raise_for_status()
                text = response.json()["choices"][0]["message"]["content"] or ""
                parsed = _parse_json(text)
                logger.info(
                    "model reply <- %s in %.1fs: %s",
                    model,
                    time.monotonic() - started,
                    _gist(json.dumps(parsed, ensure_ascii=False), 300),
                )
                return parsed
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last = exc
                logger.warning("explorer llm call failed (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(2 * (attempt + 1))
    raise LLMError(f"model call failed after {attempts} attempts: {last}")


def _gist(text: str, limit: int) -> str:
    """One line, cut short: enough to follow a run in the log."""
    line = " ".join(text.split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model reply: {text[:200]!r}")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model reply is not a JSON object")
    return parsed
