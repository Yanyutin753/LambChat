"""A filename must not turn SVG or corrupt bytes into model image input."""

import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage
from PIL import Image

from src.infra.agent.middleware.tool_interception import ToolResultBinaryMiddleware


class Request:
    def __init__(self, messages):
        self.messages = messages

    def override(self, **kwargs):
        return Request(kwargs.get("messages", self.messages))


async def capture(request):
    return request


@pytest.fixture
def read_image(monkeypatch):
    async def read(content, path="/workspace/slide.png"):
        uploaded = []
        events = []

        class Backend:
            async def adownload_files(self, paths):
                return [SimpleNamespace(content=content)]

        class Storage:
            async def upload_file(self, file, folder, filename, content_type, **kwargs):
                uploaded.append((file.read(), filename, content_type))
                return SimpleNamespace(key=f"{folder}/{filename}", content_type=content_type)

        class Presenter:
            def present_tool_start(self, *args, **kwargs):
                return {"event": "start", **kwargs}

            def present_tool_result(self, *args, **kwargs):
                return {"event": "result", **kwargs}

            async def emit(self, event):
                events.append(event)

        async def storage():
            return Storage()

        monkeypatch.setattr("src.infra.storage.s3.service.get_or_init_storage", storage)
        monkeypatch.setattr(
            "src.infra.tool.backend_utils.get_backend_from_runtime", lambda runtime: Backend()
        )
        middleware = ToolResultBinaryMiddleware(
            base_url="https://app.example.com", supports_vision=True
        )
        request = SimpleNamespace(
            runtime=SimpleNamespace(config={"configurable": {"presenter": Presenter()}}),
            tool_call={"name": "read_file", "id": "call-1", "args": {"file_path": path}},
        )

        async def handler(request):
            raise AssertionError("Invalid images must not fall through to the binary reader")

        message = await middleware.awrap_tool_call(request, handler)
        outbound = Request([message])
        result = await middleware.awrap_model_call(outbound, capture)
        return message, uploaded, events, result, outbound

    return read


async def test_svg_disguised_as_png_extracts_nested_unicode_text_and_keeps_preview(read_image):
    content = b'\xef\xbb\xbf<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><text>'
    content += "抖音 <tspan>与快手</tspan> &amp; B站".encode()
    content += b"</text><script>do not extract this</script><text>Next</text></svg>"
    message, uploaded, events, result, outbound = await read_image(content)
    payload = json.loads(message.content)
    assert payload["text"] == "抖音 与快手 & B站\nNext"
    assert payload["mime_type"] == "image/svg+xml"
    assert payload["name"] == "slide.svg"
    assert uploaded == [(content, "slide.svg", "image/svg+xml")]
    assert result is outbound
    assert events[-1]["success"] is True


async def test_svg_without_text_returns_guidance_without_model_image_input(read_image):
    content = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L1 1"/></svg>'
    message, uploaded, _, result, outbound = await read_image(content)
    payload = json.loads(message.content)
    assert payload["text"] == ""
    assert "PNG" in payload["warning"]
    assert uploaded[0][2] == "image/svg+xml"
    assert result is outbound


@pytest.mark.parametrize(
    "content",
    [
        b"not an image",
        b"<svg><text>broken",
        b'<!DOCTYPE svg [<!ENTITY secret SYSTEM "file:///etc/passwd">]><svg><text>&secret;</text></svg>',
        b"<html><text>not svg</text></html>",
    ],
)
async def test_bad_images_are_recoverable_tool_errors_and_emit_failed_results(read_image, content):
    message, uploaded, events, result, outbound = await read_image(content)
    assert isinstance(message, ToolMessage)
    assert message.status == "error"
    assert json.loads(message.content)["error"]
    assert uploaded == []
    assert events[-1]["success"] is False
    assert result is outbound


@pytest.mark.parametrize(
    "fmt,mime,ext",
    [
        ("JPEG", "image/jpeg", "jpg"),
        ("PNG", "image/png", "png"),
        ("WEBP", "image/webp", "webp"),
        ("GIF", "image/gif", "gif"),
        ("TIFF", "image/jpeg", "jpg"),
    ],
)
async def test_raster_format_comes_from_bytes_and_unsafe_formats_are_transcoded(
    read_image, monkeypatch, fmt, mime, ext
):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "src.infra.upload.file_record.FileRecordStorage.is_private_key",
        AsyncMock(return_value=False),
    )
    buffer = BytesIO()
    Image.new("RGB", (8, 6), "red").save(buffer, format=fmt)
    message, uploaded, _, result, outbound = await read_image(buffer.getvalue(), "/workspace/a.svg")
    payload = json.loads(message.content)
    assert payload["mime_type"] == mime
    assert payload["name"] == f"a.{ext}"
    with Image.open(BytesIO(uploaded[0][0])) as image:
        image.load()
        assert image.size == (8, 6)
        assert image.format == ("JPEG" if fmt == "TIFF" else fmt)
    assert result is not outbound
    assert len(result.messages) == 2


async def test_svg_text_is_bounded_and_reports_truncation(read_image):
    content = ("<svg><text>" + "字" * 30_000 + "</text></svg>").encode()
    message, _, _, result, outbound = await read_image(content)
    payload = json.loads(message.content)
    assert len(payload["text"]) <= 20_000
    assert payload["text_truncated"] is True
    assert result is outbound


async def test_truncated_raster_is_not_sent_to_model(read_image):
    buffer = BytesIO()
    Image.new("RGB", (8, 6), "red").save(buffer, format="PNG")
    message, uploaded, events, result, outbound = await read_image(buffer.getvalue()[:45])
    assert message.status == "error"
    assert not uploaded
    assert events[-1]["success"] is False
    assert result is outbound


async def test_image_pixel_limit_returns_tool_error(read_image, monkeypatch):
    monkeypatch.setattr("src.infra.image_utils.IMAGE_COMPRESSION_MAX_PIXELS", 4)
    buffer = BytesIO()
    Image.new("RGB", (8, 6), "red").save(buffer, format="PNG")
    message, uploaded, _, result, outbound = await read_image(buffer.getvalue())
    assert message.status == "error"
    assert not uploaded
    assert result is outbound


async def test_nonimage_binary_upload_is_preserved(read_image):
    content = b"%PDF-document"
    message, uploaded, _, result, outbound = await read_image(content, "/workspace/report.pdf")
    assert message.status == "success"
    assert uploaded == [(content, "report.pdf", "application/pdf")]
    assert result is outbound
