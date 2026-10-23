"""Ordinary files require an owner or a short-lived, file-scoped capability."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from src.kernel.errors import AppError


@pytest.fixture
def access(monkeypatch):
    from src.infra.upload import access

    record = {"key": "image/owner/a.png", "uploaded_by": "owner"}
    records = SimpleNamespace(
        is_private_key=AsyncMock(return_value=False),
        find_by_key=AsyncMock(return_value=record),
        require_private_access=AsyncMock(side_effect=AppError(access.ErrorCode.FILE_NOT_FOUND)),
    )
    monkeypatch.setattr(access, "get_file_record_storage", lambda: records)
    monkeypatch.setattr("src.infra.upload.shared_files.get_file_record_storage", lambda: records)
    monkeypatch.setattr(access, "_owns_generated_file", AsyncMock(return_value=False))
    monkeypatch.setattr(access.settings, "APP_BASE_URL", "https://chat.example")
    return access, records


@pytest.mark.parametrize("user", [None, "other"])
async def test_foreign_or_anonymous_key_does_not_grant_access(access, user):
    module, _ = access
    with pytest.raises(AppError):
        await module.require_file_access("image/owner/a.png", user)


async def test_owner_can_get_a_variant_capability_without_changing_the_key(access):
    module, _ = access
    url = await module.authorize_file_url(
        "https://chat.example/api/upload/file/image/owner/a.png?thumb=1", "owner"
    )
    query = parse_qs(urlsplit(url).query)
    assert query["thumb"] == ["1"]
    await module.require_file_access("image/owner/a.png", None, token=query["file_token"][0])
    with pytest.raises(AppError):
        await module.require_file_access("image/owner/b.png", None, token=query["file_token"][0])


async def test_expired_or_account_token_cannot_be_a_file_capability(access):
    from src.infra.auth.jwt import create_access_token

    module, _ = access
    expired = module.file_access_url(
        "/api/upload/file/image/owner/a.png", "image/owner/a.png", expires=-1
    )
    for token in [
        parse_qs(urlsplit(expired).query)["file_token"][0],
        create_access_token("owner"),
        "invalid",
    ]:
        with pytest.raises(AppError):
            await module.require_file_access("image/owner/a.png", None, token=token)


async def test_private_capture_never_accepts_a_bearer_capability(access):
    module, records = access
    records.is_private_key.return_value = True
    key = "cua_screenshots/owner/session/a.png"
    url = module.file_access_url("/api/upload/file/" + key, key)
    with pytest.raises(AppError):
        await module.require_file_access(
            key, None, token=parse_qs(urlsplit(url).query)["file_token"][0]
        )


async def test_external_url_with_upload_path_is_not_signed(access):
    module, records = access
    url = "https://evil.example/api/upload/file/image/owner/a.png"
    assert await module.authorize_file_url(url, "owner") == url
    records.find_by_key.assert_not_awaited()


@pytest.mark.parametrize(
    "flags",
    [
        {},
        {"direct": True},
        {"proxy": True},
        {"thumb": True},
        {"cover": True},
        {"resolve_resources": True},
    ],
)
async def test_download_variants_reject_a_leaked_key_before_storage(access, monkeypatch, flags):
    from src.api.routes import upload

    module, records = access
    monkeypatch.setattr(upload, "_file_record_storage", records)
    storage = AsyncMock()
    monkeypatch.setattr(upload, "get_or_init_storage", storage)
    with pytest.raises(AppError):
        await upload.get_file_proxy(
            "image/owner/a.png", SimpleNamespace(), current_user=None, **flags
        )
    storage.assert_not_awaited()


async def test_generated_upload_registers_owner_before_return(monkeypatch):
    from io import BytesIO

    from src.infra.logging.context import TraceContext
    from src.infra.storage.s3.service import S3StorageService
    from src.infra.storage.s3.types import UploadResult
    from src.infra.upload.file_record import FileRecordStorage

    service = S3StorageService()
    result = UploadResult(
        key="revealed_files/a.png",
        url="/api/upload/file/revealed_files/a.png",
        size=3,
        content_type="image/png",
    )
    monkeypatch.setattr(
        service, "_get_backend", lambda: SimpleNamespace(upload=AsyncMock(return_value=result))
    )
    register = AsyncMock()
    monkeypatch.setattr(FileRecordStorage, "register_generated", register, raising=False)
    TraceContext.set_request_context(user_id="owner", session_id="session")
    try:
        assert await service.upload_file(BytesIO(b"abc"), "revealed_files", "a.png") is result
    finally:
        TraceContext.clear_request_context()
    register.assert_awaited_once_with(result, "owner", "session")


async def test_revoking_share_invalidates_its_file_token(access, monkeypatch):
    from datetime import datetime, timezone

    from src.infra.share.storage import ShareStorage

    module, _ = access
    share = SimpleNamespace(share_id="shared", updated_at=datetime.now(timezone.utc))
    url = module.file_access_url(
        "/api/upload/file/image/owner/a.png", "image/owner/a.png", share=share
    )
    monkeypatch.setattr(ShareStorage, "get_by_share_id", AsyncMock(return_value=None))
    with pytest.raises(AppError):
        await module.require_file_access(
            "image/owner/a.png", None, token=parse_qs(urlsplit(url).query)["file_token"][0]
        )


async def test_share_projection_only_grants_owner_files_and_preserves_variants(access, monkeypatch):
    from datetime import datetime, timezone

    from src.infra.upload import shared_files

    module, _ = access
    share = SimpleNamespace(
        owner_id="owner", share_id="share", updated_at=datetime.now(timezone.utc)
    )
    monkeypatch.setattr(
        shared_files, "owned_file_keys", AsyncMock(return_value={"image/owner/a.png"})
    )
    events = [
        {
            "text": "![photo](https://chat.example/api/upload/file/image/owner/a.png?thumb=1) ![foreign](/api/upload/file/image/other/b.png)",
            "tool": '{"url":"/api/upload/file/image/owner/a.png"}',
        }
    ]
    projected = await shared_files.authorize_shared_files(events, share)
    assert "file_token=" in projected[0]["text"]
    assert "thumb=1" in projected[0]["text"]
    assert "/image/other/b.png)" in projected[0]["text"]
    assert "file_token=" in projected[0]["tool"]
    assert "file_token=" not in events[0]["text"]


async def test_shared_text_resources_are_scoped_to_file_owner_and_read_is_bounded(
    access, monkeypatch
):
    from datetime import datetime, timezone

    from src.infra.upload import shared_files

    monkeypatch.setattr(
        shared_files, "related_file_keys", AsyncMock(return_value={"image/owner/a.png"})
    )

    share = SimpleNamespace(
        owner_id="owner", share_id="share", updated_at=datetime.now(timezone.utc)
    )
    monkeypatch.setattr(
        shared_files, "owned_file_keys", AsyncMock(return_value={"image/owner/a.png"})
    )

    async def stream(key):
        yield b'<img src="/api/upload/file/image/owner/a.png"><img src="/api/upload/file/image/other/b.png">'

    storage = SimpleNamespace(download_stream=stream)
    text = await shared_files.read_authorized_file_text(
        storage, "document/owner/a.html", "owner", share=share
    )
    assert "file_token=" in text
    assert '/image/other/b.png"' in text
    monkeypatch.setattr(shared_files, "TEXT_PREVIEW_MAX_BYTES", 10)
    with pytest.raises(AppError):
        await shared_files.read_authorized_file_text(
            storage, "document/owner/a.html", "owner", share=share
        )


@pytest.mark.parametrize("flags", [{}, {"direct": True}, {"thumb": True}, {"cover": True}])
async def test_shared_download_never_exposes_object_storage_capability(access, monkeypatch, flags):
    from datetime import datetime, timezone

    from starlette.responses import Response

    from src.api.routes import upload
    from src.infra.share.storage import ShareStorage

    module, records = access
    share = SimpleNamespace(
        owner_id="owner", share_id="share", updated_at=datetime.now(timezone.utc)
    )
    key = "image/owner/a.png"
    token = parse_qs(
        urlsplit(module.file_access_url("/api/upload/file/" + key, key, share=share)).query
    )["file_token"][0]
    monkeypatch.setattr(ShareStorage, "get_by_share_id", AsyncMock(return_value=share))
    monkeypatch.setattr(upload, "_file_record_storage", records)
    storage = SimpleNamespace(
        is_local=False,
        _config=SimpleNamespace(public_bucket=False),
        file_exists=AsyncMock(return_value=True),
        get_presigned_url=AsyncMock(return_value="https://storage.example/signed"),
    )

    async def stream(key):
        yield b"file"

    storage.download_stream = stream
    monkeypatch.setattr(upload, "get_or_init_storage", AsyncMock(return_value=storage))
    monkeypatch.setattr(upload, "get_model_safe_file_response", AsyncMock(return_value=None))
    monkeypatch.setattr(
        upload.upload_preview,
        "get_file_response_metadata",
        AsyncMock(return_value=("a.png", "image/png")),
    )
    monkeypatch.setattr(upload, "_get_base_url", lambda _: "https://chat.example")
    variant = AsyncMock(return_value=Response(b"thumb"))
    monkeypatch.setattr(upload, "get_file_image_variant_response", variant)
    response = await upload.get_file_proxy(
        key, SimpleNamespace(headers={}), current_user=None, file_token=token, **flags
    )
    assert response.status_code == 200
    storage.get_presigned_url.assert_not_awaited()
    if flags.get("cover") or flags.get("thumb"):
        assert variant.call_args.args[3] is True
    else:
        assert b"".join([chunk async for chunk in response.body_iterator]) == b"file"


def test_storage_key_length_is_bounded_before_parent_lookup(access):
    module, _ = access
    with pytest.raises(AppError):
        module.validate_file_key("a/" * 512 + "a")
    with pytest.raises(AppError):
        module.validate_file_key("图" * 342)


def test_application_storage_rejects_public_buckets():
    from src.infra.storage.s3.service import S3StorageService
    from src.infra.storage.s3.types import S3Config, S3Provider

    config = S3Config(provider=S3Provider.ALIYUN, public_bucket=True)
    with pytest.raises(ValueError, match="private bucket"):
        S3StorageService(config)
    with pytest.raises(ValueError, match="private bucket"):
        S3StorageService().configure(config)


async def test_existing_foreign_record_cannot_be_overridden_by_revealed_fallback(access):
    module, records = access
    records.find_by_key.side_effect = lambda key, owner=None: (
        None if owner else {"key": key, "uploaded_by": "other"}
    )
    module._owns_generated_file.return_value = True
    with pytest.raises(AppError):
        await module.require_file_access("revealed_files/a.png", "owner")


async def test_shared_nested_text_references_request_resource_projection(access, monkeypatch):
    from src.infra.upload import shared_files

    monkeypatch.setattr(
        shared_files, "related_file_keys", AsyncMock(return_value={"document/owner/style.css"})
    )

    monkeypatch.setattr(
        shared_files, "owned_file_keys", AsyncMock(return_value={"document/owner/style.css"})
    )

    async def stream(key):
        yield b'<link href="/api/upload/file/document/owner/style.css">'

    text = await shared_files.read_authorized_file_text(
        SimpleNamespace(download_stream=stream), "document/owner/a.html", "owner"
    )
    assert "resolve_resources=true" in text


async def test_authorized_text_preview_resolves_resources_using_the_primary_file_owner(
    access, monkeypatch
):
    from src.api.routes import upload
    from src.infra.upload import shared_files

    _, records = access
    records.find_by_key.return_value = {
        "key": "document/owner/page.html",
        "uploaded_by": "owner",
        "hash": "generated:document/owner/page.html",
        "resource_keys": ["image/owner/a.png"],
        "name": "page.html",
        "mime_type": "text/html",
    }
    monkeypatch.setattr(upload, "_file_record_storage", records)
    monkeypatch.setattr(
        shared_files, "owned_file_keys", AsyncMock(return_value={"image/owner/a.png"})
    )

    async def stream(key):
        yield b'<img src="/api/upload/file/image/owner/a.png">'

    storage = SimpleNamespace(download_stream=stream)
    monkeypatch.setattr(upload, "get_or_init_storage", AsyncMock(return_value=storage))
    response = await upload.get_file_proxy(
        "document/owner/page.html",
        SimpleNamespace(headers={}),
        current_user=SimpleNamespace(sub="owner"),
        resolve_resources=True,
    )
    assert response.status_code == 200
    assert b"file_token=" in response.body
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize(
    "url",
    [
        "//evil.example/api/upload/file/image/owner/a.png",
        "https://evil.example/path/api/upload/file/image/owner/a.png",
        "https://evil.example\\/api/upload/file/image/owner/a.png",
    ],
)
async def test_share_does_not_sign_substrings_inside_foreign_resource_urls(
    access, monkeypatch, url
):
    from src.infra.upload import shared_files

    monkeypatch.setattr(
        shared_files, "owned_file_keys", AsyncMock(return_value={"image/owner/a.png"})
    )
    original = f'<img src="{url}">'
    assert await shared_files.authorize_owned_files(original, "owner") == original


async def test_batch_signing_checks_unknown_keys_with_bounded_database_queries(access, monkeypatch):
    from unittest.mock import Mock

    from src.api.routes import upload, upload_signed_urls
    from src.infra.revealed_file import storage as revealed_storage
    from src.infra.upload import shared_files

    module, records = access
    records.find_by_key.return_value = None

    async def empty():
        if False:
            yield {}

    records.collection = SimpleNamespace(find=Mock(side_effect=lambda *_: empty()))
    revealed = SimpleNamespace(
        collection=SimpleNamespace(find=Mock(side_effect=lambda *_: empty()))
    )
    monkeypatch.setattr(upload, "_file_record_storage", records)
    monkeypatch.setattr(shared_files, "get_file_record_storage", lambda: records)
    monkeypatch.setattr(revealed_storage, "get_revealed_file_storage", lambda: revealed)
    monkeypatch.setattr(upload, "_get_base_url", lambda _: "https://chat.example")
    result = await upload_signed_urls.get_signed_urls(
        upload_signed_urls.SignedUrlRequest(keys=[f"image/other/{n}.png" for n in range(100)]),
        SimpleNamespace(),
        current_user=SimpleNamespace(sub="owner"),
    )
    assert len(result.urls) == 100 and all(item.error and not item.url for item in result.urls)
    assert records.find_by_key.await_count + records.collection.find.call_count <= 1
    assert revealed.collection.find.call_count <= 1
