"""Repeated credential/billing failures should go directly to the configured fallback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from src.infra.agent.middleware.retry import ModelFallbackMiddleware


class Request:
    def __init__(self, model):
        self.model = model

    def override(self, **kwargs):
        return Request(kwargs.get("model", self.model))


@pytest.mark.parametrize("status,expected_primary", [(401, 2), (402, 2), (429, 3)])
async def test_account_failures_cool_down_across_middleware_instances(
    monkeypatch, status, expected_primary
):
    primary = SimpleNamespace(
        quota_model_config_id=str(uuid4()),
        openai_api_key=SecretStr("key-one"),
        model_name="primary",
    )
    fallback = SimpleNamespace(model_name="fallback")
    calls = []

    async def handler(request):
        calls.append(request.model)
        if request.model is primary:
            r = httpx.Response(status, request=httpx.Request("POST", "https://unit.invalid/chat"))
            raise httpx.HTTPStatusError("account unavailable", request=r.request, response=r)
        return AIMessage(content="fallback answer")

    async def direct(self, request, wrapped):
        return await wrapped(request)

    monkeypatch.setattr(ModelFallbackMiddleware, "_schedule_prewarm", lambda self: None)
    monkeypatch.setattr(
        ModelFallbackMiddleware, "_get_fallback_llm", AsyncMock(return_value=fallback)
    )
    monkeypatch.setattr(ModelFallbackMiddleware, "_with_fallback_image_mode", direct)
    for _ in range(3):
        result = await ModelFallbackMiddleware(fallback_model="fallback").awrap_model_call(
            Request(primary), handler
        )
        assert result.content == "fallback answer"

    assert sum(m is primary for m in calls) == expected_primary
    assert sum(m is fallback for m in calls) == 3

    if status == 402:
        primary.openai_api_key = SecretStr("replacement-key")
        await ModelFallbackMiddleware(fallback_model="fallback").awrap_model_call(
            Request(primary), handler
        )
        assert sum(m is primary for m in calls) == 3
    elif status == 401:
        from src.infra.agent.middleware import retry

        now = retry.monotonic()
        monkeypatch.setattr(retry, "monotonic", lambda: now + 601)
        await ModelFallbackMiddleware(fallback_model="fallback").awrap_model_call(
            Request(primary), handler
        )
        assert sum(m is primary for m in calls) == 3
