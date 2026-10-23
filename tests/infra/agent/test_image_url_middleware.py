import asyncio
import logging

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from src.infra.agent.middleware.image_url import (
    ImageUrlProxyDirectMiddleware,
    ImageUrlToBase64Middleware,
    _append_proxy_direct_param,
    _with_data_url,
)


@pytest.fixture(autouse=True)
def authorized_transport_urls(monkeypatch):
    from unittest.mock import AsyncMock

    async def authorize(url, *args, **kwargs):
        return url

    monkeypatch.setattr("src.kernel.config.settings.APP_BASE_URL", "https://lambchat.com")
    monkeypatch.setattr("src.infra.upload.access.authorize_file_url", authorize)
    monkeypatch.setattr(
        "src.infra.upload.file_record.FileRecordStorage.is_private_key",
        AsyncMock(side_effect=lambda key: key.startswith("cua_screenshots/")),
    )


async def test_base64_preparation_overlaps_images_with_bounded_concurrency(monkeypatch):
    active = peak = 0
    release = asyncio.Event()
    four_started = asyncio.Event()

    async def download(url, mime):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 4:
            four_started.set()
        try:
            await release.wait()
            return f"data:{mime};base64,{url.rsplit('/', 1)[-1]}"
        finally:
            active -= 1

    monkeypatch.setattr(
        "src.infra.agent.middleware.image_url._download_image_url_as_data_url", download
    )
    messages = [
        HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": f"https://cdn/{i}.png"}}
                for i in range(start, start + 5)
            ]
        )
        for start in (0, 5)
    ]
    task = asyncio.create_task(ImageUrlToBase64Middleware()._convert_messages(messages))
    try:
        await asyncio.wait_for(four_started.wait(), 0.5)
        assert peak == 4
    finally:
        release.set()
        converted = await task
    assert peak == 4
    assert active == 0
    assert [b["image_url"]["url"] for m in converted for b in m.content] == [
        f"data:image/png;base64,{i}.png" for i in range(10)
    ]
    assert messages[0].content[0]["image_url"]["url"] == "https://cdn/0.png"


async def test_cancelling_base64_preparation_drains_inflight_downloads(monkeypatch):
    active = 0
    started = asyncio.Event()

    async def download(url, mime):
        nonlocal active
        active += 1
        if active == 4:
            started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    monkeypatch.setattr(
        "src.infra.agent.middleware.image_url._download_image_url_as_data_url", download
    )
    message = HumanMessage(
        content=[
            {"type": "image_url", "image_url": {"url": f"https://cdn/{i}.png"}} for i in range(10)
        ]
    )
    task = asyncio.create_task(ImageUrlToBase64Middleware()._convert_messages([message]))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active == 0


def test_anthropic_image_block_uses_compressed_data_url_mime_type():
    converted = _with_data_url(
        {
            "type": "image",
            "source": {
                "type": "url",
                "url": "https://app.example.com/source.png",
                "media_type": "image/png",
            },
        },
        "data:image/jpeg;base64,Y29tcHJlc3NlZA==",
    )

    assert converted["source"]["media_type"] == "image/jpeg"


async def test_image_url_middleware_converts_model_request_blocks(monkeypatch):
    async def fake_download(url, mime_type):
        assert url == "https://app.example.com/api/upload/file/uploads/img.png"
        assert mime_type == "image/png"
        return "data:image/png;base64,aW1hZ2U="

    monkeypatch.setattr(
        "src.infra.agent.middleware.image_url._download_image_url_as_data_url",
        fake_download,
    )

    class Request:
        def __init__(self, messages):
            self.messages = messages

        def override(self, **kwargs):
            return Request(kwargs.get("messages", self.messages))

    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    middleware = ImageUrlToBase64Middleware()
    message = HumanMessage(
        content=[
            {"type": "text", "text": "what is this?"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://app.example.com/api/upload/file/uploads/img.png",
                    "mime_type": "image/png",
                },
            },
        ]
    )

    await middleware.awrap_model_call(Request([message]), handler)

    converted = seen["request"].messages[0]
    assert converted is not message
    assert converted.content[1]["image_url"]["url"] == "data:image/png;base64,aW1hZ2U="
    assert "original_url" not in converted.content[1]

    payload = ChatOpenAI(api_key="test")._get_request_payload([converted])
    assert "original_url" not in payload["messages"][0]["content"][1]


async def test_image_url_middleware_failure_log_omits_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    secret_url = "https://cdn.example.test/image.png?signature=private-token"

    async def _fail_download(_url: str, _mime_type: str):
        raise RuntimeError(f"failed to fetch {secret_url}")

    monkeypatch.setattr(
        "src.infra.agent.middleware.image_url._download_image_url_as_data_url",
        _fail_download,
    )
    middleware = ImageUrlToBase64Middleware()

    with caplog.at_level(logging.WARNING):
        messages = await middleware._convert_messages(
            [HumanMessage(content=[{"type": "image_url", "image_url": {"url": secret_url}}])]
        )
        content = messages[0].content

    assert content[0]["image_url"]["url"] == secret_url
    assert secret_url not in caplog.text
    assert "RuntimeError" in caplog.text


# ---------- ImageUrlProxyDirectMiddleware ----------


def test_append_proxy_direct_param_adds_param_to_upload_url():
    url = "https://lambchat.com/api/upload/file/image/u1/a.png"
    assert _append_proxy_direct_param(url) == url + "?proxy=true"


def test_append_proxy_direct_param_preserves_existing_query():
    url = "https://lambchat.com/api/upload/file/image/u1/a.png?x=1"
    assert _append_proxy_direct_param(url) == url + "&proxy=true"


def test_append_proxy_direct_param_is_idempotent():
    url = "https://lambchat.com/api/upload/file/image/u1/a.png?proxy=true"
    assert _append_proxy_direct_param(url) == url


def test_append_proxy_direct_param_ignores_external_urls():
    url = "https://cdn.example.com/image/a.png"
    assert _append_proxy_direct_param(url) == url


def test_append_proxy_direct_param_ignores_data_urls():
    url = "data:image/png;base64,aW1hZ2U="
    assert _append_proxy_direct_param(url) == url


async def test_proxy_direct_middleware_rewrites_upload_image_blocks():
    class Request:
        def __init__(self, messages):
            self.messages = messages

        def override(self, **kwargs):
            return Request(kwargs.get("messages", self.messages))

    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    middleware = ImageUrlProxyDirectMiddleware()
    message = HumanMessage(
        content=[
            {"type": "text", "text": "what is this?"},
            {
                "type": "image_url",
                "image_url": {
                    "url": "https://lambchat.com/api/upload/file/image/u1/a.png",
                    "mime_type": "image/png",
                },
            },
            {
                "type": "image_url",
                "image_url": {"url": "https://cdn.example.com/image/b.png"},
            },
        ]
    )

    await middleware.awrap_model_call(Request([message]), handler)

    rewritten = seen["request"].messages[0]
    assert rewritten is not message
    assert (
        rewritten.content[1]["image_url"]["url"]
        == "https://lambchat.com/api/upload/file/image/u1/a.png?proxy=true"
    )
    assert rewritten.content[2]["image_url"]["url"] == "https://cdn.example.com/image/b.png"


async def test_proxy_direct_middleware_rewrites_anthropic_url_source_blocks():
    class Request:
        def __init__(self, messages):
            self.messages = messages

        def override(self, **kwargs):
            return Request(kwargs.get("messages", self.messages))

    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    middleware = ImageUrlProxyDirectMiddleware()
    message = HumanMessage(
        content=[
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": "https://lambchat.com/api/upload/file/image/u1/c.png",
                    "media_type": "image/png",
                },
            },
        ]
    )

    await middleware.awrap_model_call(Request([message]), handler)

    rewritten = seen["request"].messages[0]
    assert (
        rewritten.content[0]["source"]["url"]
        == "https://lambchat.com/api/upload/file/image/u1/c.png?proxy=true"
    )


async def test_proxy_direct_middleware_keeps_reference_when_nothing_changed():
    class Request:
        def __init__(self, messages):
            self.messages = messages

        def override(self, **kwargs):
            return Request(kwargs.get("messages", self.messages))

    seen = {}

    async def handler(request):
        seen["request"] = request
        return request

    middleware = ImageUrlProxyDirectMiddleware()
    message = HumanMessage(content=[{"type": "text", "text": "no images here"}])

    await middleware.awrap_model_call(Request([message]), handler)

    assert seen["request"].messages is message or seen["request"].messages == [message]


async def test_storage_direct_resolves_only_own_urls_without_mutating_history(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.agent.middleware.image_url import image_url_middleware_for_mode
    from src.infra.storage.s3 import service
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "APP_BASE_URL", "https://lambchat.com")
    storage = SimpleNamespace(
        is_local=False,
        get_presigned_url=AsyncMock(return_value="https://storage.example/a.png?signed=fresh"),
    )
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))

    class Request:
        def __init__(self, messages):
            self.messages = messages

        def override(self, **kwargs):
            return Request(kwargs.get("messages", self.messages))

    async def handler(request):
        return request

    own = "https://lambchat.com/api/upload/file/image/u1/a.png?proxy=true"
    foreign = "https://other.example/api/upload/file/image/u1/a.png"
    message = HumanMessage(
        content=[
            {"type": "image_url", "image_url": {"url": own}},
            {"type": "image", "source": {"type": "url", "url": own}},
            {"type": "image_url", "image_url": {"url": foreign}},
        ]
    )
    middleware = image_url_middleware_for_mode("storage_direct")
    assert middleware is not None
    result = await middleware.awrap_model_call(Request([message]), handler)
    assert (
        result.messages[0].content[0]["image_url"]["url"]
        == "https://storage.example/a.png?signed=fresh"
    )
    assert (
        result.messages[0].content[1]["source"]["url"]
        == "https://storage.example/a.png?signed=fresh"
    )
    assert result.messages[0].content[2]["image_url"]["url"] == foreign
    assert message.content[0]["image_url"]["url"] == own
    storage.get_presigned_url.assert_awaited_once_with("image/u1/a.png")


async def test_storage_direct_does_not_sign_private_capture_urls(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.agent.middleware.image_url import image_url_middleware_for_mode
    from src.infra.storage.s3 import service
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "APP_BASE_URL", "https://lambchat.com")
    storage = SimpleNamespace(is_local=False, get_presigned_url=AsyncMock())
    monkeypatch.setattr(service, "get_or_init_storage", AsyncMock(return_value=storage))
    request = SimpleNamespace(
        messages=[
            HumanMessage(
                content=[
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://lambchat.com/api/upload/file/cua_screenshots/another-user/private.png"
                        },
                    }
                ]
            )
        ]
    )

    async def handler(request):
        return request

    from src.kernel.errors import AppError

    with pytest.raises(AppError):
        await image_url_middleware_for_mode("storage_direct").awrap_model_call(request, handler)
    storage.get_presigned_url.assert_not_awaited()
