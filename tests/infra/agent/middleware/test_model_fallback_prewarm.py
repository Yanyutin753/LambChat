"""ModelFallback 后台预热 fallback 客户端。

生产测量（2026-09-17 yang）：主模型 400/503 失败往往在数秒全链路往返后才
暴露，此时才开始创建 fallback 客户端会叠加查库/解密/建连的冷启动。首次
模型调用即后台预热，失败切换时 fallback 客户端已就绪（LLMClient LRU 去重，
重复创建无副作用）。
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage

from src.infra.agent.middleware.retry import ModelFallbackMiddleware
from src.infra.llm.client import LLMClient


class _FakeRequest:
    def __init__(self, model: str = "primary") -> None:
        self.model = model

    def override(self, **kwargs):  # noqa: ANN003
        clone = _FakeRequest(model=kwargs.get("model", self.model))
        return clone


def _ok_response(text: str = "ok") -> AIMessage:
    return AIMessage(content=text)


async def test_first_model_call_prewarms_fallback_client(monkeypatch) -> None:
    get_model = AsyncMock(return_value=_ok_response("fallback-instance"))
    monkeypatch.setattr(LLMClient, "get_model", get_model)

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")

    async def handler(request: _FakeRequest) -> AIMessage:  # noqa: ARG001
        return _ok_response()

    response = await middleware.awrap_model_call(_FakeRequest(), handler)

    assert response.content == "ok"
    await asyncio.sleep(0)
    await middleware._prewarm_task
    get_model.assert_awaited_once()
    assert get_model.await_args.kwargs["model"] == "deepseek-flash"


async def test_failure_reuses_prewarmed_client_without_recreate(monkeypatch) -> None:
    fallback_instance = _ok_response("fallback-instance")
    get_model = AsyncMock(return_value=fallback_instance)
    monkeypatch.setattr(LLMClient, "get_model", get_model)

    async def handler(request: _FakeRequest) -> AIMessage:
        if request.model == "primary":
            raise RuntimeError("primary exploded")
        return _ok_response("fallback answer")

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")
    response = await middleware.awrap_model_call(_FakeRequest(), handler)

    assert response.content == "fallback answer"
    get_model.assert_awaited_once()


async def test_prewarm_failure_still_allows_fallback_creation(monkeypatch) -> None:
    fallback_instance = _ok_response("fallback-instance")
    get_model = AsyncMock(side_effect=[RuntimeError("prewarm boom"), fallback_instance])
    monkeypatch.setattr(LLMClient, "get_model", get_model)

    async def handler(request: _FakeRequest) -> AIMessage:
        if request.model == "primary":
            raise RuntimeError("primary exploded")
        return _ok_response("fallback answer")

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")
    response = await middleware.awrap_model_call(_FakeRequest(), handler)

    assert response.content == "fallback answer"
    assert get_model.await_count == 2
