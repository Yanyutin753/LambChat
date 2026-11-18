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

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage

import src.agents.core.node_utils as node_utils_module
import src.infra.agent.middleware.image_url as image_url_module
from src.infra.agent.middleware.retry import ModelFallbackMiddleware
from src.infra.llm.client import LLMClient


@pytest.fixture(autouse=True)
def authorized_transport_urls(monkeypatch):
    async def authorize(url, *args, **kwargs):
        return url

    monkeypatch.setattr("src.kernel.config.settings.APP_BASE_URL", "https://lambchat.com")
    monkeypatch.setattr("src.infra.upload.access.authorize_file_url", authorize)
    monkeypatch.setattr(
        "src.infra.upload.file_record.FileRecordStorage.is_private_key",
        AsyncMock(return_value=False),
    )


_IMAGE_URL = "https://lambchat.com/api/upload/file/image/u1/f.png"


def _messages_with_image() -> list[HumanMessage]:
    return [
        HumanMessage(
            content=[
                {"type": "text", "text": "看图"},
                {"type": "image_url", "image_url": {"url": _IMAGE_URL}},
            ]
        )
    ]


async def _run_fallback(monkeypatch, mode: str, primary_mode: str = "url") -> list:
    get_model = AsyncMock(return_value=AIMessage(content="fallback-instance"))
    monkeypatch.setattr(LLMClient, "get_model", get_model)
    monkeypatch.setattr(
        node_utils_module,
        "resolve_model_image_url_mode",
        AsyncMock(return_value=mode),
    )
    seen: list = []

    async def handler(request: ModelRequest) -> AIMessage:
        if request.model == "primary":
            raise RuntimeError("primary exploded")
        seen.append(request.messages)
        return AIMessage(content="fallback answer")

    middleware = ModelFallbackMiddleware(fallback_model="deepseek-flash")
    transport = image_url_module.image_url_middleware_for_mode(primary_mode)
    original = _messages_with_image()

    async def inner(request):
        return await transport.awrap_model_call(request, handler)

    response = await middleware.awrap_model_call(
        ModelRequest(model="primary", messages=original), inner
    )
    assert _image_url_of(original[0].content) == _IMAGE_URL
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


async def test_base64_primary_does_not_download_fallback_storage_link(monkeypatch):
    signed = "https://oss.example.com/signed"
    download = AsyncMock(return_value="data:image/png;base64,QUJD")
    monkeypatch.setattr(image_url_module, "_download_image_url_as_data_url", download)
    monkeypatch.setattr(
        image_url_module, "_resolve_storage_image_url", AsyncMock(return_value=signed)
    )

    content = await _run_fallback(monkeypatch, mode="storage_direct", primary_mode="base64")

    assert _image_url_of(content) == signed
    assert [call.args[0] for call in download.await_args_list] == [_IMAGE_URL]


@pytest.mark.parametrize("primary", ["url", "base64", "storage_direct", "proxy_direct"])
@pytest.mark.parametrize("fallback", ["url", "base64", "storage_direct", "proxy_direct"])
async def test_each_attempt_prepares_original_images_once(monkeypatch, primary, fallback):
    prepare = AsyncMock(wraps=image_url_module.prepare_image_messages)
    monkeypatch.setattr(image_url_module, "prepare_image_messages", prepare)
    monkeypatch.setattr(
        image_url_module,
        "_resolve_storage_image_url",
        AsyncMock(return_value="https://oss.example.test/signed"),
    )
    monkeypatch.setattr(
        image_url_module,
        "_download_image_url_as_data_url",
        AsyncMock(return_value="data:image/png;base64,QUJD"),
    )

    await _run_fallback(monkeypatch, mode=fallback, primary_mode=primary)

    assert [call.kwargs["mode"] for call in prepare.await_args_list] == [primary, fallback]
    assert all(
        _image_url_of(call.args[0][0].content) == _IMAGE_URL for call in prepare.await_args_list
    )
