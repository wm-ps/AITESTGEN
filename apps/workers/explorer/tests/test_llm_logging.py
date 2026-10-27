"""Every model call leaves a two-line trail in the worker log: what it asked
for, and the gist of the reply (llm.ask_json)."""

import asyncio
import logging

import httpx
import pytest
from explorer_worker import llm


def test_model_call_and_reply_are_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"pick": 2}'}}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(llm, "LITELLM_BASE_URL", "http://gateway")
    monkeypatch.setattr(
        llm.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(reply), **kw),
    )
    with caplog.at_level(logging.INFO, logger="explorer_worker.llm"):
        call = llm.ask_json("system", "Goal: find the policy\nscreen…", images=[b"x"])
        result = asyncio.run(call)
    assert result == {"pick": 2}
    lines = [r.getMessage() for r in caplog.records]
    assert any(
        line.startswith("model call -> ") and "(+1 image)" in line and "find the policy" in line
        for line in lines
    )
    assert any(line.startswith("model reply <- ") and '{"pick": 2}' in line for line in lines)
