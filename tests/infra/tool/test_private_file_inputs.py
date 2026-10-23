"""Tools reading uploaded URLs must retain owner access after uploads become private."""

import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from src.infra.upload.file_record import FileRecordStorage
from src.kernel.errors import AppError


@pytest.mark.parametrize(
    "tool_name,extension", [("image", "png"), ("audio", "wav"), ("document", "pdf")]
)
@pytest.mark.parametrize("owned", [True, False])
async def test_uploaded_tool_input_requires_owner_and_authorizes_http(
    monkeypatch, tool_name, extension, owned
):
    from src.infra.tool import audio_transcribe_tool, document_parse_tool, image_generation_tool

    monkeypatch.setattr(
        FileRecordStorage,
        "find_by_key",
        AsyncMock(return_value={"uploaded_by": "owner"} if owned else None),
    )
    monkeypatch.setattr(
        "src.infra.upload.access._owns_generated_file", AsyncMock(return_value=False)
    )
    requests = []

    class Response:
        headers = {"content-type": "image/png"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def raise_for_status(self):
            pass

        async def aiter_bytes(self):
            yield b"file bytes"

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url):
            requests.append(url)
            assert parse_qs(urlsplit(url).query).get("file_token"), (
                "private app download needs a capability"
            )
            return Response()

    monkeypatch.setattr(image_generation_tool, "_get_download_client", lambda: Client())
    monkeypatch.setattr(audio_transcribe_tool.httpx, "AsyncClient", lambda **kwargs: Client())
    monkeypatch.setattr(audio_transcribe_tool, "unpriced_usage", nullcontext)
    transcribe = AsyncMock(return_value=SimpleNamespace(text="transcribed"))
    monkeypatch.setattr(
        audio_transcribe_tool,
        "_build_client",
        lambda: SimpleNamespace(
            audio=SimpleNamespace(transcriptions=SimpleNamespace(create=transcribe)),
            aclose=AsyncMock(),
        ),
    )
    parse = AsyncMock(return_value={"markdown": "parsed", "images": []})
    monkeypatch.setattr(document_parse_tool, "execute_document_parse", parse)
    monkeypatch.setattr(document_parse_tool.settings, "DOCUMENT_PARSE_MAX_DOWNLOAD_BYTES", 1024)
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "context": SimpleNamespace(user_id="owner"),
                "session_id": "session",
                "base_url": "https://app.example",
            }
        }
    )
    original = f"/api/upload/file/{tool_name}/owner/source.{extension}"
    if tool_name == "image":
        if owned:
            file, _, _ = await image_generation_tool._download_image_source(original, runtime)
            assert file.read() == b"file bytes"
            file.close()
        else:
            with pytest.raises(AppError):
                await image_generation_tool._download_image_source(original, runtime)
    else:
        tool = (
            audio_transcribe_tool.audio_transcribe
            if tool_name == "audio"
            else document_parse_tool.document_parse
        )
        result = json.loads(await tool.coroutine(url=original, runtime=runtime))
        assert bool(result.get("success")) is owned
        assert "file_token=" not in json.dumps(result)
    if owned:
        assert len(requests) == 1
    else:
        assert requests == []
        transcribe.assert_not_awaited()
        parse.assert_not_awaited()
