"""Authorized private media can seek without exposing storage capabilities."""

import asyncio
from importlib import import_module, util
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import Request

from src.kernel.errors import AppError, ErrorCode

KEY = "video/owner/movie.mp4"
SIGNED_URL = "https://storage.example/movie.mp4?Signature=private-storage-secret"


def _module():
    assert util.find_spec("src.api.routes.upload_range") is not None, (
        "Private media Range streaming is not implemented"
    )
    return import_module("src.api.routes.upload_range")


class _Stream(httpx.AsyncByteStream):
    def __init__(self):
        self.started = False
        self.closed = False

    async def __aiter__(self):
        self.started = True
        yield b"a" * 100_000
        yield b"b" * 100_000

    async def aclose(self):
        self.closed = True


@pytest.fixture
async def upstream(monkeypatch):
    module = _module()
    stream = _Stream()
    requests = []
    clients = []
    source = SimpleNamespace(
        status=206,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": "200000",
            "Content-Range": "bytes 10-200009/300000",
            "Accept-Ranges": "bytes",
            "Location": SIGNED_URL,
            "Set-Cookie": "storage_secret=must-not-leak",
            "X-Storage-Token": "must-not-leak",
        },
        error=None,
    )

    def respond(request):
        requests.append(request)
        if source.error is not None:
            raise source.error
        return httpx.Response(
            source.status,
            headers=source.headers,
            stream=stream if len(requests) == 1 else _Stream(),
        )

    client_class = httpx.AsyncClient

    def make_client(**kwargs):
        client = client_class(transport=httpx.MockTransport(respond), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(module.httpx, "AsyncClient", make_client)
    storage = SimpleNamespace(get_presigned_url=AsyncMock(return_value=SIGNED_URL))
    async with module.create_range_client() as client:
        yield (
            SimpleNamespace(
                get_private_range_response=lambda *args: module.get_private_range_response(
                    *args, client=client
                )
            ),
            storage,
            source,
            stream,
            requests,
            clients,
        )
    assert client.is_closed


async def test_partial_media_uses_one_signed_request_and_bounded_raw_chunks(upstream):
    module, storage, _, stream, requests, clients = upstream
    response = await module.get_private_range_response(storage, KEY, "bytes=10-200009")

    assert response.status_code == 206
    assert not stream.started
    assert not clients[0].is_closed
    chunks = [chunk async for chunk in response.body_iterator]
    assert b"".join(chunks) == b"a" * 100_000 + b"b" * 100_000
    assert max(map(len, chunks)) <= 64 * 1024
    assert len(requests) == 1
    assert requests[0].headers["range"] == "bytes=10-200009"
    assert requests[0].headers["accept-encoding"] == "identity"
    assert "authorization" not in requests[0].headers
    assert "cookie" not in requests[0].headers
    storage.get_presigned_url.assert_awaited_once_with(KEY, 60)
    assert stream.closed
    assert not clients[0].is_closed


async def test_only_media_headers_are_returned_to_the_browser(upstream):
    module, storage, _, _, _, _ = upstream
    response = await module.get_private_range_response(storage, KEY, "bytes=10-200009")
    assert dict(response.headers) == {
        "content-type": "video/mp4",
        "content-length": "200000",
        "content-range": "bytes 10-200009/300000",
        "accept-ranges": "bytes",
        "cache-control": "private, no-store",
        "vary": "Authorization",
    }
    await response.background()


async def test_storage_ignoring_range_still_streams_a_200_without_buffering(upstream):
    module, storage, source, stream, _, clients = upstream
    source.status = 200
    source.headers.pop("Content-Range")
    response = await module.get_private_range_response(storage, KEY, "bytes=0-")
    assert response.status_code == 200
    assert not stream.started
    assert b"".join([chunk async for chunk in response.body_iterator]) == (
        b"a" * 100_000 + b"b" * 100_000
    )
    assert not clients[0].is_closed


async def test_unsatisfiable_range_does_not_expose_the_storage_error_body(upstream):
    module, storage, source, stream, _, clients = upstream
    source.status = 416
    source.headers["Content-Range"] = "bytes */300000"
    response = await module.get_private_range_response(storage, KEY, "bytes=400000-")
    assert response.status_code == 416
    assert response.body == b""
    assert response.headers["content-range"] == "bytes */300000"
    assert response.headers["content-length"] == "0"
    assert "location" not in response.headers
    assert not stream.started
    assert stream.closed
    assert not clients[0].is_closed


@pytest.mark.parametrize("status", [301, 302, 307, 401, 403, 404, 500])
async def test_redirects_and_storage_failures_close_resources_without_leaking(upstream, status):
    module, storage, source, stream, requests, clients = upstream
    source.status = status
    with pytest.raises(AppError) as error:
        await module.get_private_range_response(storage, KEY, "bytes=0-")
    assert error.value.error_code.code == (
        "file_not_found" if status == 404 else "file_read_failed"
    )
    assert len(requests) == 1
    assert not stream.started
    assert stream.closed
    assert not clients[0].is_closed


async def test_abandoning_a_partial_stream_closes_only_its_upstream(upstream):
    module, storage, _, stream, _, clients = upstream
    response = await module.get_private_range_response(storage, KEY, "bytes=10-200009")
    first = await anext(response.body_iterator)
    assert len(first) <= 64 * 1024
    await response.body_iterator.aclose()
    assert stream.closed
    assert not clients[0].is_closed
    await response.background()


async def test_connection_failure_preserves_the_shared_client(upstream):
    module, storage, source, _, _, clients = upstream
    source.error = httpx.ConnectError("storage unavailable")
    with pytest.raises(AppError) as error:
        await module.get_private_range_response(storage, KEY, "bytes=0-")
    assert error.value.error_code.code == "file_read_failed"
    assert not clients[0].is_closed


async def test_disconnect_before_first_body_chunk_also_closes_resources(upstream):
    from starlette.requests import ClientDisconnect

    module, storage, _, stream, _, clients = upstream
    response = await module.get_private_range_response(storage, KEY, "bytes=0-")

    async def disconnected_send(message):
        raise OSError("browser disconnected")

    with pytest.raises(ClientDisconnect):
        await response(
            {"type": "http", "asgi": {"spec_version": "2.4"}},
            AsyncMock(),
            disconnected_send,
        )
    assert not stream.started
    assert stream.closed
    assert not clients[0].is_closed


async def test_compressed_upstream_is_rejected_instead_of_corrupting_range_lengths(upstream):
    module, storage, source, stream, _, clients = upstream
    source.headers["Content-Encoding"] = "gzip"
    with pytest.raises(AppError) as error:
        await module.get_private_range_response(storage, KEY, "bytes=0-")
    assert error.value.error_code.code == "file_read_failed"
    assert not stream.started
    assert stream.closed
    assert not clients[0].is_closed


def _range_request():
    return Request(
        {
            "type": "http",
            "app": SimpleNamespace(state=SimpleNamespace(upload_range_client="shared-client")),
            "method": "GET",
            "scheme": "https",
            "path": "/api/upload/file/" + KEY,
            "headers": [(b"host", b"chat.example"), (b"range", b"bytes=2-5")],
            "server": ("chat.example", 443),
            "query_string": b"",
        }
    )


@pytest.mark.parametrize("shared", [False, True])
async def test_route_dispatches_authorized_nonlocal_ranges_to_the_stream_helper(
    monkeypatch, shared
):
    from starlette.responses import Response

    from src.api.routes import upload
    from src.infra.upload import access

    module = _module()
    storage = SimpleNamespace(is_local=False, file_exists=AsyncMock(return_value=True))
    monkeypatch.setattr(
        upload,
        "_file_record_storage",
        SimpleNamespace(is_private_key=AsyncMock(return_value=False)),
    )
    monkeypatch.setattr(upload, "get_or_init_storage", AsyncMock(return_value=storage))
    monkeypatch.setattr(upload, "get_model_safe_file_response", AsyncMock(return_value=None))
    monkeypatch.setattr(
        access,
        "require_file_access",
        AsyncMock(return_value=SimpleNamespace(share_id="explicit-share") if shared else None),
    )
    stream = AsyncMock(return_value=Response(b"2345", status_code=206))
    monkeypatch.setattr(module, "get_private_range_response", stream)
    response = await upload.get_file_proxy(
        KEY, _range_request(), proxy=not shared, current_user=SimpleNamespace(sub="owner")
    )
    assert response.status_code == 206
    assert response.body == b"2345"
    stream.assert_awaited_once_with(storage, KEY, "bytes=2-5", client="shared-client")
    storage.file_exists.assert_not_awaited()


async def test_route_never_opens_a_range_stream_for_an_unauthorized_key(monkeypatch):
    from src.api.routes import upload
    from src.infra.upload import access

    module = _module()
    monkeypatch.setattr(
        upload,
        "_file_record_storage",
        SimpleNamespace(is_private_key=AsyncMock(return_value=False)),
    )
    monkeypatch.setattr(
        access, "require_file_access", AsyncMock(side_effect=AppError(ErrorCode.FILE_NOT_FOUND))
    )
    initialize = AsyncMock()
    stream = AsyncMock()
    monkeypatch.setattr(upload, "get_or_init_storage", initialize)
    monkeypatch.setattr(module, "get_private_range_response", stream)
    with pytest.raises(AppError) as error:
        await upload.get_file_proxy(
            KEY, _range_request(), proxy=True, current_user=SimpleNamespace(sub="other")
        )
    assert error.value.error_code.code == "file_not_found"
    initialize.assert_not_awaited()
    stream.assert_not_awaited()


async def test_local_range_still_uses_the_existing_file_response(monkeypatch, tmp_path):
    from starlette.responses import FileResponse

    from src.api.routes import upload
    from src.infra.upload import access

    module = _module()
    path = tmp_path / "movie.mp4"
    path.write_bytes(b"0123456789")
    storage = SimpleNamespace(is_local=True, get_file_path=lambda key: path)
    monkeypatch.setattr(
        upload,
        "_file_record_storage",
        SimpleNamespace(
            is_private_key=AsyncMock(return_value=False),
            find_by_key=AsyncMock(return_value={"name": "movie.mp4", "mime_type": "video/mp4"}),
        ),
    )
    monkeypatch.setattr(upload, "get_or_init_storage", AsyncMock(return_value=storage))
    monkeypatch.setattr(access, "require_file_access", AsyncMock(return_value=None))
    stream = AsyncMock(side_effect=AssertionError("local file opened a remote stream"))
    monkeypatch.setattr(module, "get_private_range_response", stream)
    request = _range_request()
    response = await upload.get_file_proxy(
        KEY, request, proxy=True, current_user=SimpleNamespace(sub="owner")
    )
    assert isinstance(response, FileResponse)
    messages = []

    async def send(message):
        messages.append(message)

    incoming = asyncio.Queue()
    incoming.put_nowait({"type": "http.request", "body": b"", "more_body": False})
    await response(request.scope, incoming.get, send)
    assert messages[0]["status"] == 206
    assert b"".join(message.get("body", b"") for message in messages[1:]) == b"2345"
    stream.assert_not_awaited()


async def test_reused_pool_never_replays_storage_cookies(upstream):
    module, storage, _, _, requests, clients = upstream
    for _ in range(2):
        response = await module.get_private_range_response(storage, KEY, "bytes=0-")
        _ = [chunk async for chunk in response.body_iterator]
    assert len(clients) == 1
    assert len(requests) == 2
    assert all(
        "cookie" not in request.headers and "authorization" not in request.headers
        for request in requests
    )
    assert not clients[0].is_closed


async def test_abandoned_stream_does_not_close_another_request(upstream):
    module, storage, _, _, _, clients = upstream
    first = await module.get_private_range_response(storage, KEY, "bytes=0-")
    second = await module.get_private_range_response(storage, KEY, "bytes=0-")
    await first.background()
    assert not clients[0].is_closed
    assert len(b"".join([chunk async for chunk in second.body_iterator])) == 200000
