"""双通道全灭的终判行为(issue #1140)。

生产首例(2026-10-30):主模型 zai 瞬时 500 → fallback 撞上 deepseek 内容风控
400 → 任务以裸上游 JSON 失败。锁定三件事:纯瞬时主模型回切重放一次、全灭
打点 ``fallback_exhausted``、风控 400 映射为可行动文案而不是透传。
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain_core.messages import AIMessage

from src.infra.agent.middleware.retry import ModelFallbackMiddleware
from src.infra.llm.client import LLMClient
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode


class _FakeRequest:
    def __init__(self, model: str = "primary") -> None:
        self.model = model
        self.messages = []

    def override(self, **kwargs):  # noqa: ANN003
        return _FakeRequest(model=kwargs.get("model", self.model))


def _transient_500() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://unit.invalid/v1/messages")
    response = httpx.Response(500, request=request)
    return httpx.HTTPStatusError("upstream exploded", request=request, response=response)


def _content_blocked_400() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://unit.invalid/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return httpx.HTTPStatusError(
        "Error code: 400 - {'error': {'message': 'Content Exists Risk (request_id: 0xabc)'}}",
        request=request,
        response=response,
    )


@pytest.fixture(autouse=True)
def _no_replay_delay(monkeypatch):
    monkeypatch.setattr(settings, "LLM_RETRY_DELAY", 0)
    monkeypatch.setattr(LLMClient, "get_model", AsyncMock(return_value="fallback-instance"))


async def test_transient_primary_replayed_once_after_fallback_dies():
    calls: list[str] = []

    async def handler(request: _FakeRequest) -> AIMessage:
        if request.model == "primary":
            calls.append("primary")
            if calls.count("primary") == 1:
                raise _transient_500()
            return AIMessage(content="recovered by primary replay")
        calls.append("fallback")
        raise _content_blocked_400()

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")
    response = await middleware.awrap_model_call(_FakeRequest(), handler)

    assert response.content == "recovered by primary replay"
    assert calls == ["primary", "fallback", "primary"]


async def test_double_failure_maps_content_moderation_and_emits_exhausted_metric(caplog):
    async def handler(request: _FakeRequest) -> AIMessage:
        if request.model == "primary":
            raise _transient_500()
        raise _content_blocked_400()

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(AppError) as exc_info:
            await middleware.awrap_model_call(_FakeRequest(), handler)

    assert exc_info.value.error_code is ErrorCode.MODEL_CONTENT_BLOCKED
    assert "safety policy" in exc_info.value.display_message
    assert "fallback_exhausted" in caplog.text
    assert "reason=transient" in caplog.text
    # 上游原始 JSON(含 request_id)不进入打点行
    assert "request_id" not in caplog.text


async def test_primary_content_block_maps_even_when_fallback_dies_plainly():
    async def handler(request: _FakeRequest) -> AIMessage:
        if request.model == "primary":
            raise _content_blocked_400()
        raise RuntimeError("fallback channel dead")

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")
    with pytest.raises(AppError) as exc_info:
        await middleware.awrap_model_call(_FakeRequest(), handler)

    assert exc_info.value.error_code is ErrorCode.MODEL_CONTENT_BLOCKED


async def test_non_transient_primary_failure_keeps_raw_error_without_replay():
    calls: list[str] = []

    async def handler(request: _FakeRequest) -> AIMessage:
        calls.append(request.model)
        if request.model == "primary":
            raise ValueError("malformed tool payload")
        raise RuntimeError("fallback channel dead")

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")
    with pytest.raises(RuntimeError, match="fallback channel dead"):
        await middleware.awrap_model_call(_FakeRequest(), handler)

    assert calls.count("primary") == 1
