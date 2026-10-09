from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.routes import upload
from src.infra.session.storage import SessionStorage
from src.infra.upload.file_record import FileRecordStorage
from src.kernel.errors import AppError

KEY = "cua_screenshots/owner/session/a.png"


@pytest.fixture
def screenshot(monkeypatch):
    record = {
        "uploaded_by": "owner",
        "private_session_id": "session",
        "mime_type": "image/png",
        "name": "screenshot.png",
    }
    records = FileRecordStorage()
    records.find_by_key = AsyncMock(return_value=record)
    sessions = SimpleNamespace(
        collection=SimpleNamespace(find_one=AsyncMock(return_value={"user_id": "owner"}))
    )
    monkeypatch.setattr(upload, "_file_record_storage", records)
    monkeypatch.setattr(SessionStorage, "__new__", lambda cls: sessions)
    storage = SimpleNamespace(
        is_local=False,
        _config=SimpleNamespace(public_bucket=False),
        file_exists=AsyncMock(return_value=True),
        download_stream=Mock(return_value=iter([])),
        get_presigned_url=AsyncMock(),
    )
    monkeypatch.setattr(upload, "get_or_init_storage", AsyncMock(return_value=storage))
    req = SimpleNamespace(
        base_url="https://app.example/",
        headers={"host": "app.example"},
        url=SimpleNamespace(scheme="https"),
    )
    return record, sessions, storage, req


@pytest.mark.parametrize("user", [None, SimpleNamespace(sub="other")])
@pytest.mark.parametrize(
    "flags", [{}, {"cover": True}, {"thumb": True}, {"direct": True}, {"proxy": True}]
)
async def test_leaked_screenshot_url_never_exposes_bytes_to_anonymous_or_other_user(
    screenshot, user, flags
):
    _, _, storage, req = screenshot
    with pytest.raises(AppError):
        await upload.get_file_proxy(KEY, req, current_user=user, **flags)
    storage.get_presigned_url.assert_not_awaited()
    storage.download_stream.assert_not_called()


async def test_owner_gets_no_store_stream_and_never_a_signed_url(screenshot):
    _, _, storage, req = screenshot
    response = await upload.get_file_proxy(
        KEY, req, current_user=SimpleNamespace(sub="owner"), direct=True
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert "location" not in response.headers
    storage.get_presigned_url.assert_not_awaited()


async def test_shared_or_deleted_session_does_not_grant_screenshot_access(screenshot):
    _, sessions, _, req = screenshot
    sessions.collection.find_one.return_value = None
    with pytest.raises(AppError):
        await upload.get_file_proxy(KEY, req, current_user=SimpleNamespace(sub="owner"))


async def test_missing_record_fails_closed(screenshot):
    _, _, _, req = screenshot
    upload._file_record_storage.find_by_key.return_value = None
    with pytest.raises(AppError):
        await upload.get_file_proxy(KEY, req, current_user=SimpleNamespace(sub="owner"))


@pytest.mark.parametrize("batch", [False, True])
async def test_signed_url_routes_never_create_bearer_links_for_captures(screenshot, batch):
    from src.api.routes.upload_signed_urls import (
        SignedUrlRequest,
        get_signed_urls,
        get_single_signed_url,
    )

    _, _, storage, req = screenshot
    user = SimpleNamespace(sub="owner")
    if batch:
        result = await get_signed_urls(SignedUrlRequest(keys=[KEY]), req, current_user=user)
        url = result.urls[0].url
    else:
        result = await get_single_signed_url(KEY, req, current_user=user)
        url = result.url
    assert url == f"https://app.example/api/upload/file/{KEY}"
    storage.get_presigned_url.assert_not_awaited()


async def test_noncanonical_key_cannot_bypass_private_guard(screenshot):
    _, _, _, req = screenshot
    with pytest.raises(AppError):
        await upload.get_file_proxy("image/../" + KEY, req, current_user=None)


async def test_registered_legacy_capture_does_not_retain_public_access(screenshot):
    _, _, _, req = screenshot
    with pytest.raises(AppError):
        await upload.get_file_proxy("tool_binaries/old.png", req, current_user=None)


async def test_private_thumbnail_resizes_without_public_copy_or_redirect(screenshot):
    import io

    from PIL import Image

    _, _, storage, req = screenshot
    buffer = io.BytesIO()
    Image.new("RGB", (3840, 2160), "blue").save(buffer, format="PNG")
    data = buffer.getvalue()

    async def download_stream(key):
        yield data

    storage.download_stream = download_stream
    response = await upload.get_file_proxy(
        KEY, req, current_user=SimpleNamespace(sub="owner"), thumb=True
    )
    assert response.media_type == "image/jpeg"
    with Image.open(io.BytesIO(response.body)) as image:
        assert image.size == (560, 315)
    assert response.headers["cache-control"] == "private, no-store"
    assert "location" not in response.headers
    storage.get_presigned_url.assert_not_awaited()
