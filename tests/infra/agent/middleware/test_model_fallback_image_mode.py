"""ModelFallback 按 fallback 模型自身配置处理出站图片。

生产事故（2026-10-11 lambchat.com run_20261011135253_4b0d2a2d）：主模型
gpt-6-astra 上游授权失效逐调用 fallback，旧实现给 fallback 硬编码
ImageUrlStorageDirectMiddleware，无视 fallback 模型配置的 image_url_mode，
DeepSeek 拉取 OSS 预签名直链间歇 400 "Failed to download image"。修复后
fallback 与主模型同规则：按 fallback 模型 profile 配置的 image_url_mode
决定图片 URL 处理方式，"url" 档不做任何改写。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage, HumanMessage

import src.agents.core.node_utils as node_utils_module
import src.infra.agent.middleware.image_url as image_url_module
from src.infra.agent.middleware.retry import ModelFallbackMiddleware
from src.infra.llm.client import LLMClient

_IMAGE_URL = "https://lambchat.com/api/upload/file/image/u1/f.png"


class _FakeRequest:
    def __init__(self, model: str = "primary", messages: list | None = None) -> None:
        self.model = model
        self.messages = messages if messages is not None else []

    def override(self, **kwargs):  # noqa: ANN003
        return _FakeRequest(
            model=kwargs.get("model", self.model),
            messages=kwargs.get("messages", self.messages),
        )


def _messages_with_image() -> list[HumanMessage]:
    return [
        HumanMessage(
            content=[
                {"type": "text", "text": "看图"},
                {"type": "image_url", "image_url": {"url": _IMAGE_URL}},
            ]
        )
    ]


async def _run_fallback(monkeypatch, mode: str) -> list:
    get_model = AsyncMock(return_value=AIMessage(content="fallback-instance"))
    monkeypatch.setattr(LLMClient, "get_model", get_model)
    monkeypatch.setattr(
        node_utils_module,
        "resolve_model_image_url_mode",
        AsyncMock(return_value=mode),
    )
    seen: list = []

    async def handler(request: _FakeRequest) -> AIMessage:
        if request.model == "primary":
            raise RuntimeError("primary exploded")
        seen.append(request.messages)
        return AIMessage(content="fallback answer")

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")
    response = await middleware.awrap_model_call(
        _FakeRequest(messages=_messages_with_image()), handler
    )
    assert response.content == "fallback answer"
    assert seen, "fallback handler must have been invoked"
    return seen[0][0].content


def _image_url_of(content: list) -> str:
    blocks = [
        block for block in content if isinstance(block, dict) and block.get("type") == "image_url"
    ]
    assert blocks, "image block must survive into the fallback call"
    return blocks[0]["image_url"]["url"]


async def test_fallback_mode_url_passes_images_through(monkeypatch) -> None:
    monkeypatch.setattr(
        image_url_module,
        "_resolve_storage_image_url",
        AsyncMock(return_value="https://oss.example.com/signed"),
    )
    content = await _run_fallback(monkeypatch, mode="url")
    assert _image_url_of(content) == _IMAGE_URL


async def test_fallback_mode_base64_inlines_images(monkeypatch) -> None:
    monkeypatch.setattr(
        image_url_module,
        "_download_image_url_as_data_url",
        AsyncMock(return_value="data:image/png;base64,QUJD"),
    )
    content = await _run_fallback(monkeypatch, mode="base64")
    assert _image_url_of(content).startswith("data:image/png;base64,")


async def test_fallback_mode_storage_direct_uses_resolved_url(monkeypatch) -> None:
    monkeypatch.setattr(
        image_url_module,
        "_resolve_storage_image_url",
        AsyncMock(return_value="https://oss.example.com/signed"),
    )
    content = await _run_fallback(monkeypatch, mode="storage_direct")
    assert _image_url_of(content) == "https://oss.example.com/signed"
