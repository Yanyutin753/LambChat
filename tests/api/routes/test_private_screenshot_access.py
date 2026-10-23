from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.api.routes import upload
from src.infra.session.storage import SessionStorage
from src.infra.upload import access, shared_files
from src.infra.upload.file_record import FileRecordStorage
from src.kernel.errors import AppError

KEY = "cua_screenshots/owner/session/a.png"


async def _documents(docs):
    for doc in docs:
        yield dict(doc)


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
    records.ensure_indexes_if_needed = AsyncMock()
    records._collection = SimpleNamespace(
        find=Mock(side_effect=lambda query: _documents([{**record, "key": KEY}]))
    )
    sessions = SimpleNamespace(
        collection=SimpleNamespace(
            find_one=AsyncMock(return_value={"user_id": "owner"}),
            find=Mock(
                side_effect=lambda query, projection: _documents(
                    [{"session_id": "session", "user_id": "owner"}]
                )
            ),
        )
    )
    monkeypatch.setattr(upload, "_file_record_storage", records)
    monkeypatch.setattr(access, "get_file_record_storage", lambda: records)
    monkeypatch.setattr(shared_files, "get_file_record_storage", lambda: records)
    revealed = SimpleNamespace(
        collection=SimpleNamespace(find=Mock(side_effect=lambda query: _documents([])))
    )
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage", lambda: revealed
    )
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
    "flags",
    [
        {},
        {"cover": True},
        {"thumb": True},
        {"direct": True},
        {"proxy": True},
        {"thumb": True, "proxy": True},
        {"cover": True, "proxy": True},
    ],
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


@pytest.mark.parametrize("count", [1, 100])
async def test_batch_signed_urls_queries_records_and_sessions_once(screenshot, count):
    from src.api.routes.upload_signed_urls import SignedUrlRequest, get_signed_urls

    record, sessions, storage, req = screenshot
    keys = [f"tool_binaries/owner/session/{index}.png" for index in range(count)]
    records = upload._file_record_storage
    records._collection.find.side_effect = lambda query: _documents(
        [{**record, "key": key} for key in keys]
    )
    result = await get_signed_urls(
        SignedUrlRequest(keys=keys), req, current_user=SimpleNamespace(sub="owner")
    )

    assert [item.key for item in result.urls] == keys
    assert all(
        item.url == f"https://app.example/api/upload/file/{item.key}" for item in result.urls
    )
    assert result.expires_in == 0
    records._collection.find.assert_called_once_with({"key": {"$in": keys}})
    records.find_by_key.assert_not_awaited()
    sessions.collection.find.assert_called_once()
    sessions.collection.find_one.assert_not_awaited()
    storage.get_presigned_url.assert_not_awaited()


async def test_batch_signed_urls_preserves_denials_fallback_and_duplicate_results(screenshot):
    from src.api.routes.upload_signed_urls import SignedUrlRequest, get_signed_urls

    record, sessions, storage, req = screenshot
    keys = [KEY, "cua_screenshots/missing.png", "tool_binaries/legacy.png", KEY]
    denied = {
        "foreign": {"uploaded_by": "other"},
        "deleting": {"deleting_at": "now"},
        "stale": {"private_capture_epoch": 1},
        "missing-session": {"private_session_id": "gone"},
    }
    keys.extend(f"tool_binaries/{name}.png" for name in denied)
    upload._file_record_storage._collection.find.side_effect = lambda query: _documents(
        [{**record, "key": KEY}, {"key": "tool_binaries/legacy.png", "uploaded_by": "owner"}]
        + [
            {**record, **flags, "key": f"tool_binaries/{name}.png"}
            for name, flags in denied.items()
        ]
    )
    storage.get_presigned_url.return_value = "https://signed.example/legacy"

    result = await get_signed_urls(
        SignedUrlRequest(keys=keys), req, current_user=SimpleNamespace(sub="owner")
    )

    private_keys = [key for key in keys if key != "tool_binaries/legacy.png"]
    assert [item.key for item in result.urls] == [*private_keys, "tool_binaries/legacy.png"]
    for item in result.urls[:-1]:
        assert (item.url is not None) == (item.key == KEY)
        assert item.error == (None if item.key == KEY else "File not found")
    assert result.urls[-1].url == "https://signed.example/legacy"
    storage.get_presigned_url.assert_awaited_once_with("tool_binaries/legacy.png", 3600)
    # Capture authorization and the legacy owner's ordinary-file lookup share this fixture.
    assert upload._file_record_storage._collection.find.call_count == 2


async def test_batch_signed_urls_rejects_session_delete_marker(screenshot):
    from src.api.routes.upload_signed_urls import SignedUrlRequest, get_signed_urls

    _, sessions, storage, req = screenshot
    sessions.collection.find.side_effect = lambda query, projection: _documents([])
    result = await get_signed_urls(
        SignedUrlRequest(keys=[KEY]), req, current_user=SimpleNamespace(sub="owner")
    )

    assert result.urls[0].error == "File not found"
    query = sessions.collection.find.call_args.args[0]
    assert query["user_id"] == "owner"
    assert query["attachment_delete_operation"] == {"$exists": False}
    storage.get_presigned_url.assert_not_awaited()


async def test_batch_signed_urls_isolates_public_signing_errors(screenshot):
    from src.api.routes.upload_signed_urls import SignedUrlRequest, get_signed_urls

    _, _, storage, req = screenshot
    storage.get_presigned_url.side_effect = [
        RuntimeError("unavailable"),
        "https://signed.example/ok",
    ]
    upload._file_record_storage._collection.find.side_effect = lambda query: _documents(
        [{"key": key, "uploaded_by": "owner"} for key in query["key"]["$in"]]
    )
    result = await get_signed_urls(
        SignedUrlRequest(keys=["image/bad.png", "image/ok.png"]),
        req,
        current_user=SimpleNamespace(sub="owner"),
    )

    assert [item.key for item in result.urls] == ["image/bad.png", "image/ok.png"]
    assert result.urls[0].error == "unavailable"
    assert result.urls[1].url == "https://signed.example/ok"
    upload._file_record_storage._collection.find.assert_called_once()


async def test_private_batch_lookup_rejects_oversized_keys_before_query(screenshot):
    with pytest.raises(ValueError, match="Too many file keys"):
        await upload._file_record_storage.get_private_key_access(
            [f"cua_screenshots/{index}.png" for index in range(101)], "owner"
        )
    upload._file_record_storage._collection.find.assert_not_called()


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


async def test_owner_local_capture_remains_an_authenticated_file_response(
    screenshot, monkeypatch, tmp_path
):
    from starlette.responses import FileResponse

    _, _, original_storage, req = screenshot
    path = tmp_path / "capture.png"
    path.write_bytes(b"private-capture")
    storage = SimpleNamespace(is_local=True, get_file_path=lambda key: path)
    monkeypatch.setattr(upload, "get_or_init_storage", AsyncMock(return_value=storage))
    response = await upload.get_file_proxy(
        KEY, req, current_user=SimpleNamespace(sub="owner"), direct=True
    )
    assert isinstance(response, FileResponse)
    assert response.path == str(path)
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert "location" not in response.headers
    original_storage.get_presigned_url.assert_not_awaited()
