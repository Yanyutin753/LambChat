"""Check binary media on the SDK's actual HTTP boundary, including compatible APIs."""

import base64
import json
from copy import deepcopy
from io import BytesIO

import httpx
import pytest
from google import genai
from google.genai.types import HttpOptions
from langchain_core.messages import AIMessage, HumanMessage
from PIL import Image

from src.infra.llm.google_chat import LambChatGoogleChatModel


@pytest.mark.parametrize("entry", ["invoke", "ainvoke", "stream", "astream"])
async def test_google_media_uses_standard_base64_on_the_wire(entry):
    image = BytesIO()
    Image.new("RGB", (8, 8), (253, 254, 255)).save(image, format="PNG")
    raw = image.getvalue()
    encoded = base64.b64encode(raw).decode()
    assert "+" in encoded or "/" in encoded
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        response = {
            "candidates": [
                {"content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP"}
            ]
        }
        if "streamGenerateContent" in request.url.path:
            return httpx.Response(
                200,
                text="data: " + json.dumps(response) + "\n\n",
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=response)

    transport = httpx.MockTransport(respond)
    sdk = genai.Client(
        api_key="test",
        http_options=HttpOptions(
            base_url="https://model.invalid",
            httpx_client=httpx.Client(transport=transport),
            httpx_async_client=httpx.AsyncClient(transport=transport),
        ),
    )
    model = LambChatGoogleChatModel(model="gemini-4-argon", api_key="test")
    original_client = model.client
    model.client = sdk
    message = HumanMessage(
        content=[
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}},
        ]
    )
    history = [
        HumanMessage(content=f"history {i}") if i % 2 == 0 else AIMessage(content=f"reply {i}")
        for i in range(39)
    ]
    message.content.append(deepcopy(message.content[1]))
    try:
        payload = model._prepare_request(
            [*history, message],
            http_options={
                "headers": {"X-Validation": "preserved"},
                "extra_body": {"validationMarker": True},
            },
        )
        if entry == "invoke":
            sdk.models.generate_content(**payload)
        elif entry == "ainvoke":
            await sdk.aio.models.generate_content(**payload)
        elif entry == "stream":
            list(sdk.models.generate_content_stream(**payload))
        else:
            stream = await sdk.aio.models.generate_content_stream(**payload)
            _ = [chunk async for chunk in stream]
        assert len(captured) == 1
        assert captured[0]["validationMarker"] is True
        media = captured[0]["contents"][39]["parts"][2]["inlineData"]
        assert media.get("mimeType", media.get("mime_type")) == "image/png"
        assert base64.b64decode(media["data"], validate=True) == raw
        assert media["data"] == encoded
        assert message.content[1]["image_url"]["url"] == "data:image/png;base64," + encoded
    finally:
        sdk.close()
        await sdk.aio.aclose()
        model.client = original_client
        await model.aclose()
