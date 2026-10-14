import base64

import pytest

from src.infra.sandbox.workspace_preview import read_workspace_preview


async def test_stream_preview_does_not_buffer_or_base64_encode():
    async def read(*_args):
        raise AssertionError("binary text read")

    async def download(*_args):
        raise AssertionError("buffered download")

    yielded = []

    async def stream(_path):
        for chunk in [b"\x00", b"\xff"]:
            yielded.append(chunk)
            yield chunk

    result = await read_workspace_preview(
        "image.png", 0, 500, read=read, download=download, stream=stream
    )
    assert yielded == []
    assert await anext(result) == b"\x00"
    assert yielded == [b"\x00"]
    assert await anext(result) == b"\xff"


@pytest.mark.parametrize("path", ["image.PNG", "archive.zip", "report.pdf"])
async def test_binary_preview_transfers_exact_bytes_without_text_read(path):
    async def read(*_args):
        raise AssertionError("binary previews must not read lossy text")

    async def download(_path):
        return b"\x00\xff\x80"

    result = await read_workspace_preview(path, 0, 500, read=read, download=download)
    assert result["encoding"] == "base64"
    assert base64.b64decode(result["content"]) == b"\x00\xff\x80"


@pytest.mark.parametrize(
    "error",
    [
        "file too large to read directly: 3000000 bytes (limit 2097152 bytes)",
        "Binary file exceeds maximum preview size of 512000 bytes",
    ],
)
async def test_preview_uses_same_large_file_fallback_for_local_and_cloud(error):
    async def read(*_args):
        return {"error": error}

    async def download(_path):
        return b"\x00\xff"

    result = await read_workspace_preview("unknown", 0, 500, read=read, download=download)
    assert result == {"encoding": "base64", "content": "AP8="}


async def test_text_preview_preserves_paging_and_errors():
    async def download(_path):
        raise AssertionError("text/permission errors must not trigger downloads")

    for response in [
        {"encoding": "utf-8", "content": "second line", "next_offset": 2},
        {"error": "permission_denied"},
    ]:

        async def read(path, offset, limit):
            assert (path, offset, limit) == ("notes.txt", 1, 1)
            return response

        assert (
            await read_workspace_preview("notes.txt", 1, 1, read=read, download=download)
            == response
        )


@pytest.mark.parametrize("payload", [b"", "file_too_large", "permission_denied"])
async def test_binary_preview_preserves_empty_file_and_transfer_errors(payload):
    async def read(*_args):
        raise AssertionError("binary previews must transfer directly")

    async def download(_path):
        return payload

    result = await read_workspace_preview("archive.zip", 0, 500, read=read, download=download)
    assert result == (
        {"encoding": "base64", "content": ""} if payload == b"" else {"error": payload}
    )
