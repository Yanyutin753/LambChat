"""Images from tool observations must reach the model without changing stored results."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.infra.agent.middleware.tool_interception import ToolResultBinaryMiddleware


class Request:
    def __init__(self, messages):
        self.messages = messages

    def override(self, **kwargs):
        return Request(kwargs.get("messages", self.messages))


async def capture(request):
    return request


@pytest.mark.parametrize("tool_name", ["read_file", "computer_use"])
async def test_tool_image_is_injected_only_into_the_outbound_model_request(tool_name):
    image = {"url": "/api/upload/file/tool_binaries/chart.png", "mime_type": "image/png"}
    payload = image if tool_name == "read_file" else {"screenshot": {**image, "mime": "image/png"}}
    message = ToolMessage(content=json.dumps(payload), name=tool_name, tool_call_id="call-1")
    original = Request([AIMessage(content=""), message])
    result = await ToolResultBinaryMiddleware(
        base_url="https://app.example.com", supports_vision=True
    ).awrap_model_call(original, capture)
    assert original.messages == [AIMessage(content=""), message]
    assert result.messages[:-1] == original.messages
    assert isinstance(result.messages[-1], HumanMessage)
    assert result.messages[-1].content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://app.example.com/api/upload/file/tool_binaries/chart.png"},
    }
    assert isinstance(message.content, str)
    assert "base64" not in message.content


async def test_nonvision_model_does_not_receive_image_blocks():
    request = Request(
        [
            ToolMessage(
                content=json.dumps({"url": "/api/upload/file/a.png", "mime_type": "image/png"}),
                name="read_file",
                tool_call_id="call-1",
            )
        ]
    )
    result = await ToolResultBinaryMiddleware(supports_vision=False).awrap_model_call(
        request, capture
    )
    assert result is request


async def test_old_observations_are_not_reinjected_after_the_model_has_replied():
    request = Request(
        [
            ToolMessage(
                content='{"url":"/api/upload/file/a.png","mime_type":"image/png"}',
                name="read_file",
                tool_call_id="call-1",
            ),
            AIMessage(content="I inspected the image."),
        ]
    )
    result = await ToolResultBinaryMiddleware(supports_vision=True).awrap_model_call(
        request, capture
    )
    assert result is request


async def test_local_tool_image_is_inlined_before_reaching_a_remote_model(monkeypatch):
    async def inline(attachments, **kwargs):
        assert kwargs["force_data_url"] is True
        return [{**attachments[0], "data_url": "data:image/png;base64,YQ=="}]

    monkeypatch.setattr(
        "src.infra.agent.middleware.tool_interception.inline_image_attachments_as_data_urls",
        inline,
        raising=False,
    )
    request = Request(
        [
            ToolMessage(
                content='{"url":"/api/upload/file/a.png","mime_type":"image/png"}',
                name="read_file",
                tool_call_id="call-1",
            )
        ]
    )
    result = await ToolResultBinaryMiddleware(
        base_url="http://127.0.0.1:8000", supports_vision=True
    ).awrap_model_call(request, capture)
    assert result.messages[-1].content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    "payload",
    [
        {"url": "/api/upload/file/a.svg", "mime_type": "image/svg+xml"},
        {"url": "http://169.254.169.254/secret", "mime_type": "image/png"},
        {"url": "https://foreign.example/api/upload/file/a.png", "mime_type": "image/png"},
        {"screenshot": {"error": "screen_recording_denied"}},
    ],
)
async def test_unsupported_or_foreign_images_are_not_promoted(payload):
    request = Request(
        [ToolMessage(content=json.dumps(payload), name="computer_use", tool_call_id="call-1")]
    )
    result = await ToolResultBinaryMiddleware(
        base_url="https://app.example.com", supports_vision=True
    ).awrap_model_call(request, capture)
    assert result is request


async def test_public_png_tool_image_keeps_its_mime_in_base64_mode(monkeypatch):
    from src.infra.agent.middleware.image_url import ImageUrlToBase64Middleware

    async def download(url, mime):
        assert mime == "image/png"
        return "data:image/png;base64,YQ=="

    monkeypatch.setattr(
        "src.infra.agent.middleware.image_url._download_image_url_as_data_url", download
    )
    request = Request(
        [
            ToolMessage(
                content='{"url":"/api/upload/file/chart.png","mime_type":"image/png"}',
                name="read_file",
                tool_call_id="call-1",
            )
        ]
    )

    async def convert(request):
        return await ImageUrlToBase64Middleware().awrap_model_call(request, capture)

    result = await ToolResultBinaryMiddleware(
        base_url="https://app.example.com", supports_vision=True
    ).awrap_model_call(request, convert)
    assert result.messages[-1].content[1]["image_url"]["url"] == "data:image/png;base64,YQ=="


async def test_pending_media_batch_deduplicates_and_bounds_image_input():
    messages = [
        ToolMessage(
            content=json.dumps({"url": f"/api/upload/file/{index}.png", "mime_type": "image/png"}),
            name="read_file",
            tool_call_id=str(index),
        )
        for index in [0, 1, 2, 3, 4, 4]
    ]
    result = await ToolResultBinaryMiddleware(
        base_url="https://app.example.com", supports_vision=True
    ).awrap_model_call(Request(messages), capture)
    images = result.messages[-1].content[1:]
    assert len(images) == 4
    assert len({image["image_url"]["url"] for image in images}) == 4


async def test_image_bridge_is_idempotent_when_a_model_request_is_retried():
    middleware = ToolResultBinaryMiddleware(
        base_url="https://app.example.com", supports_vision=True
    )
    request = Request(
        [
            ToolMessage(
                content='{"url":"/api/upload/file/a.png","mime_type":"image/png"}',
                name="read_file",
                tool_call_id="call-1",
            )
        ]
    )
    first = await middleware.awrap_model_call(request, capture)
    second = await middleware.awrap_model_call(first, capture)
    assert second is first


async def test_visual_tool_result_has_valid_openai_and_anthropic_payloads():
    from langchain_anthropic.chat_models import _format_messages
    from langchain_openai.chat_models.base import _convert_message_to_dict

    ai = AIMessage(
        content="",
        tool_calls=[{"name": "computer_use", "args": {}, "id": "call-1", "type": "tool_call"}],
    )
    tool = ToolMessage(
        content='{"screenshot":{"url":"/api/upload/file/screen.jpg","mime":"image/jpeg"}}',
        name="computer_use",
        tool_call_id="call-1",
    )
    result = await ToolResultBinaryMiddleware(
        base_url="https://app.example.com", supports_vision=True
    ).awrap_model_call(Request([ai, tool]), capture)
    openai = _convert_message_to_dict(result.messages[-1])
    assert openai["role"] == "user"
    assert openai["content"][1]["type"] == "image_url"
    _, anthropic = _format_messages(result.messages, model="claude-sonnet-4-5")
    assert anthropic[-1]["content"][-1]["type"] == "image"
    assert anthropic[-1]["content"][-1]["source"]["url"].endswith("/screen.jpg")
    assert tool.content == result.messages[1].content
