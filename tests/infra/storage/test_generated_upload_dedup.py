import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.logging.context import TraceContext
from src.infra.storage.s3.service import S3StorageService
from src.infra.storage.s3.types import S3Config, S3Provider, UploadResult


async def test_generated_same_bytes_reuse_key_after_rename_and_isolate_owners(monkeypatch):
    context = SimpleNamespace(user_id="owner-a", session_id="chat-a")
    monkeypatch.setattr(TraceContext, "get_request_context", lambda: context)
    records = SimpleNamespace(register_generated=AsyncMock())
    monkeypatch.setattr("src.infra.upload.file_record.get_file_record_storage", lambda: records)
    storage = S3StorageService(S3Config(provider=S3Provider.LOCAL))
    objects = {}

    async def upload(file, key, content_type, metadata):
        objects[key] = file.read()
        return UploadResult(
            key=key, url="/" + key, size=len(objects[key]), content_type=content_type
        )

    backend = SimpleNamespace(
        upload=AsyncMock(side_effect=upload),
        exists=AsyncMock(side_effect=lambda key: key in objects),
        get_presigned_url=AsyncMock(side_effect=lambda key, *args: "/" + key),
    )
    storage._backend = backend
    first = await storage.upload_file(
        io.BytesIO(b"same"), "revealed_files", "first.txt", "text/plain"
    )
    second = await storage.upload_file(
        io.BytesIO(b"same"), "revealed_files", "renamed.txt", "text/plain"
    )
    assert first.key == second.key
    assert backend.upload.await_count == 1
    context.user_id = "owner-b"
    other = await storage.upload_file(
        io.BytesIO(b"same"), "revealed_files", "first.txt", "text/plain"
    )
    assert other.key != first.key
    changed = await storage.upload_file(
        io.BytesIO(b"changed"), "revealed_files", "first.txt", "text/plain"
    )
    assert changed.key != other.key


async def test_overwriting_and_deleting_original_invalidates_cached_document_cover(tmp_path):
    storage = S3StorageService(S3Config(provider=S3Provider.LOCAL, storage_path=str(tmp_path)))
    key = "skills/owner/demo/report.txt"
    cover = "covers/560x315/" + key + ".jpg"
    await storage.upload_to_key(b"first", key, "text/plain")
    await storage.upload_to_key(b"old preview", cover, "image/jpeg")
    await storage.upload_to_key(b"second", key, "text/plain")
    assert not await storage.file_exists(cover)
    await storage.upload_to_key(b"new preview", cover, "image/jpeg")
    await storage.delete_file(key)
    assert not await storage.file_exists(cover)
