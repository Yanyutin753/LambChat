"""A share only grants file capabilities after explicit owner consent."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from src.kernel.errors import AppError
from src.kernel.schemas.share import ShareCreate, ShareUpdate


@pytest.fixture
def files(monkeypatch):
    from src.infra.upload import access, shared_files

    records = SimpleNamespace(
        is_private_key=AsyncMock(return_value=False),
        find_by_key=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(access, "get_file_record_storage", lambda: records)
    monkeypatch.setattr(shared_files, "get_file_record_storage", lambda: records)
    monkeypatch.setattr(access.settings, "APP_BASE_URL", "https://chat.example")
    return access, shared_files, records


def share(**overrides):
    fields = dict(
        owner_id="owner",
        share_id="shared",
        allow_files=True,
        visibility="public",
        updated_at=datetime.now(timezone.utc),
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def token_for(access, shared):
    url = access.file_access_url(
        "/api/upload/file/image/owner/a.png", "image/owner/a.png", share=shared
    )
    return parse_qs(urlsplit(url).query)["file_token"][0]


def test_share_file_consent_defaults_off_and_update_preserves_omission():
    assert ShareCreate(session_id="session").allow_files is False
    assert ShareCreate(session_id="session", allow_files=True).allow_files is True
    assert ShareUpdate().allow_files is None
    assert ShareUpdate(allow_files=False).allow_files is False


async def test_disabled_share_removes_existing_application_tokens_without_querying_ownership(
    files, monkeypatch
):
    access, shared_files, _ = files
    owned = AsyncMock(return_value={"image/owner/a.png"})
    monkeypatch.setattr(shared_files, "owned_file_keys", owned)
    url = access.file_access_url("/api/upload/file/image/owner/a.png?thumb=1", "image/owner/a.png")
    value = [{"text": url, "content": f'<img src="{url}">', "type": "html"}]
    result = await shared_files.authorize_shared_files(value, share(allow_files=False))
    assert "file_token=" not in str(result)
    assert "thumb=1" in str(result)
    assert "file_token=" in str(value)
    owned.assert_not_awaited()


async def test_legacy_share_without_consent_does_not_sign_files(files, monkeypatch):
    _, shared_files, _ = files
    owned = AsyncMock(return_value={"image/owner/a.png"})
    monkeypatch.setattr(shared_files, "owned_file_keys", owned)
    legacy = share()
    del legacy.allow_files
    value = [{"text": "/api/upload/file/image/owner/a.png http://[::1"}]
    assert await shared_files.authorize_shared_files(value, legacy) == value
    owned.assert_not_awaited()


async def test_disabled_share_rejects_a_file_token_even_with_matching_share_version(
    files, monkeypatch
):
    from src.infra.share.storage import ShareStorage

    access, _, _ = files
    shared = share(allow_files=False)
    monkeypatch.setattr(ShareStorage, "get_by_share_id", AsyncMock(return_value=shared))
    with pytest.raises(AppError):
        await access.require_file_access("image/owner/a.png", None, token=token_for(access, shared))


async def test_authenticated_share_file_capability_supports_media_requests_after_page_authorization(
    files, monkeypatch
):
    from src.infra.share.storage import ShareStorage

    access, _, _ = files
    shared = share(visibility="authenticated")
    monkeypatch.setattr(ShareStorage, "get_by_share_id", AsyncMock(return_value=shared))
    token = token_for(access, shared)
    assert await access.require_file_access("image/owner/a.png", None, token=token) is shared
    assert await access.require_file_access("image/owner/a.png", "viewer", token=token) is shared


async def test_legacy_generated_images_keep_exact_user_namespace_and_current_record_boundaries(
    files, monkeypatch
):
    from src.infra.revealed_file import storage as revealed_storage

    access, shared_files, records = files
    own = "generated-images/owner/old.png"
    foreign = "generated-images/other/old.png"
    deleted = "generated-images/owner/deleted.png"
    reowned = "generated-images/owner/reowned.png"
    docs = [
        {"key": deleted, "uploaded_by": "owner", "deleting_at": datetime.now(timezone.utc)},
        {"key": reowned, "uploaded_by": "other"},
    ]

    async def records_cursor(*_args):
        for doc in docs:
            yield doc

    async def empty(*_args):
        if False:
            yield {}

    records.collection = SimpleNamespace(find=Mock(side_effect=records_cursor))
    revealed = SimpleNamespace(collection=SimpleNamespace(find=Mock(side_effect=empty)))
    monkeypatch.setattr(revealed_storage, "get_revealed_file_storage", lambda: revealed)
    assert await shared_files.owned_file_keys({own, foreign, deleted, reowned}, "owner") == {own}
    assert await shared_files.owned_file_keys({own}, "owne") == set()
    for owner in ("anonymous", "default", "owner"):
        key = f"generated-images/{owner}/%2e%2e.png"
        assert await shared_files.owned_file_keys({key}, owner) == set()
    records.find_by_key.return_value = None
    await access.require_file_access(own, "owner")
    with pytest.raises(AppError):
        await access.require_file_access(own, "other")


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("serialized", [False, True])
async def test_share_strips_borrowed_capabilities_from_escaped_active_content(
    files, monkeypatch, enabled, serialized
):
    import json

    _, shared_files, _ = files
    monkeypatch.setattr(shared_files, "owned_file_keys", AsyncMock(return_value=set()))
    url = "/api/upload/file/image/other/a.png?thumb=1&amp;file_token=borrowed&amp;cover=true"
    value = {"type": "html", "content": f'<img src="{url}">'}
    if serialized:
        value = json.dumps(value).replace("&", "\\u0026")
    result = await shared_files.authorize_shared_files(value, share(allow_files=enabled))
    assert "borrowed" not in str(result)
    decoded = json.loads(result) if serialized else result
    assert "thumb=1" in decoded["content"] and "cover=true" in decoded["content"]


@pytest.mark.parametrize("user_id", [None, "other"])
async def test_generated_image_registration_requires_the_matching_request_owner(
    monkeypatch, user_id
):
    from io import BytesIO

    from src.infra.logging.context import TraceContext
    from src.infra.storage.s3.service import S3StorageService
    from src.infra.storage.s3.types import UploadResult
    from src.infra.upload.file_record import FileRecordStorage

    monkeypatch.setattr(FileRecordStorage, "register_generated", AsyncMock())

    service = S3StorageService()
    backend = SimpleNamespace(
        upload=AsyncMock(
            return_value=UploadResult(
                key="generated-images/owner/a.png",
                url="/api/upload/file/generated-images/owner/a.png",
                size=3,
                content_type="image/png",
            )
        )
    )
    monkeypatch.setattr(service, "_get_backend", lambda: backend)
    TraceContext.set_request_context(user_id=user_id, session_id="session")
    try:
        with pytest.raises(ValueError):
            await service.upload_file(BytesIO(b"abc"), "generated-images/owner", "a.png")
    finally:
        TraceContext.clear_request_context()
    backend.upload.assert_not_awaited()


@pytest.mark.parametrize(
    "url",
    [
        "/api/./upload/file/image/owner/a.png?file_token=borrowed",
        "/api/extra/../upload/file/image/owner/a.png?file_token=borrowed",
        "//chat.example/api/upload/file/image/owner/a.png?file_token=borrowed",
        "/api/upload/%66ile/image/owner/a.png?file_token=borrowed",
        "/%61pi/upload/file/image/owner/a.png?file_token=borrowed",
        "/api/upload/file/image/owner/tmp/../a.png?file_token=borrowed",
        "https:////chat.example/api/upload/file/image/owner/a.png?file_token=borrowed",
        "https://chat.example/api/upload/%66ile/image/owner/a.png?file_token=borrowed",
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
async def test_share_redacts_old_capabilities_from_browser_normalized_url_aliases(
    files, monkeypatch, url, enabled
):
    _, shared_files, _ = files
    monkeypatch.setattr(shared_files, "owned_file_keys", AsyncMock(return_value=set()))
    result = await shared_files.authorize_shared_files(
        {"type": "html", "content": url}, share(allow_files=enabled)
    )
    assert "borrowed" not in str(result)
