import logging

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from src.infra.agent.middleware.image_url import ImageUrlToBase64Middleware, _with_data_url


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
        content = await middleware._convert_content_blocks(
            [{"type": "image_url", "image_url": {"url": secret_url}}]
        )

    assert content[0]["image_url"]["url"] == secret_url
    assert secret_url not in caplog.text
    assert "RuntimeError" in caplog.text
