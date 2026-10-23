"""Uploaded active content must not execute with the application's origin."""

from importlib import import_module, util

import pytest
from starlette.responses import StreamingResponse


def isolation():
    assert util.find_spec("src.api.middleware.upload_isolation") is not None, (
        "Upload response isolation is missing"
    )
    return import_module("src.api.middleware.upload_isolation").UploadIsolationMiddleware


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "image/svg+xml", "application/xhtml+xml", "image/png", "video/mp4"],
)
@pytest.mark.parametrize("status", [200, 206])
async def test_uploaded_bytes_keep_streaming_and_receive_an_opaque_origin(content_type, status):
    messages = []

    async def body():
        yield b"first"
        yield b"second"

    response = StreamingResponse(body(), status_code=status, media_type=content_type)

    async def send(message):
        messages.append(message)

    await isolation()(response)(
        {"type": "http", "path": "/api/upload/file/owned/object", "asgi": {"spec_version": "2.4"}},
        None,
        send,
    )
    headers = dict(messages[0]["headers"])
    policy = headers[b"content-security-policy"].decode()
    assert policy.startswith("sandbox") and "allow-scripts" in policy
    assert "allow-same-origin" not in policy and "allow-top-navigation" not in policy
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert messages[0]["status"] == status
    assert [item["body"] for item in messages[1:]] == [b"first", b"second", b""]


async def test_normal_application_pages_are_not_sandboxed():
    messages = []

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    async def send(message):
        messages.append(message)

    await isolation()(app)({"type": "http", "path": "/"}, None, send)
    assert messages[0]["headers"] == []


def test_application_installs_upload_response_isolation():
    from src.api.main import create_app

    middleware = isolation()
    assert any(item.cls is middleware for item in create_app().user_middleware)
