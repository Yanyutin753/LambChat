"""Transcoded uploads retain verified source identity without replacing stored-byte hashes."""

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

from src.api.routes import upload, upload_image
from tests.api.routes.test_upload_model_safe import (
    _fake_request,
    _RecordingStorage,
    _tiff_bytes,
    _TranscodeUpload,
)


class Records:
    def __init__(self):
        self.rows = []
        self.race = False

    async def find_by_hash(self, digest, owner, *, source_hash_only=False):
        return next(
            (
                row.copy()
                for row in self.rows
                if row["uploaded_by"] == owner
                and "deleting_at" not in row
                and (
                    digest in row.get("source_hashes", [])
                    if source_hash_only
                    else row["hash"] == digest
                )
            ),
            None,
        )

    async def create(self, **values):
        digest = values.pop("file_hash")
        source_hash = values.pop("source_hash", None)
        row = {**values, "hash": digest}
        if source_hash:
            row["source_hashes"] = [source_hash]
        if self.race:
            self.race = False
            row["key"] = "image/owner-a/race-winner.jpg"
            row.pop("source_hashes", None)
            self.rows.append(row)
            raise DuplicateKeyError(
                "duplicate hash", 11000, {"keyPattern": {"uploaded_by": 1, "hash": 1}}
            )
        self.rows.append(row)
        return row

    async def add_source_hash(self, key, owner, source_hash):
        for row in self.rows:
            if row["key"] == key and row["uploaded_by"] == owner:
                row.setdefault("source_hashes", []).append(source_hash)

    async def delete_by_hash(self, digest, owner):
        self.rows[:] = [
            row for row in self.rows if (row["hash"], row["uploaded_by"]) != (digest, owner)
        ]

    async def refresh_owned_cleanup(self, key, owner):
        return any(
            row["key"] == key and row["uploaded_by"] == owner and "deleting_at" not in row
            for row in self.rows
        )


@pytest.fixture
def env(monkeypatch):
    records = Records()
    storage = _RecordingStorage()
    storage.file_exists = AsyncMock(return_value=True)
    storage.delete_file = AsyncMock()
    monkeypatch.setattr(upload, "_file_record_storage", records)
    monkeypatch.setattr(upload, "get_or_init_storage", AsyncMock(return_value=storage))
    monkeypatch.setattr(
        upload,
        "resolve_upload_limits",
        AsyncMock(return_value={"image": 10, "video": 10, "audio": 10, "document": 10}),
    )
    return SimpleNamespace(
        records=records,
        storage=storage,
        user=SimpleNamespace(sub="owner-a", permissions=["file:upload"], roles=[]),
        source=_tiff_bytes(),
    )


async def send(env):
    return await upload.upload_file(
        _fake_request(), _TranscodeUpload("photo.tiff", "image/tiff", env.source), env.user
    )


async def check(env, owner="owner-a"):
    return await upload.check_file_exists(
        _fake_request(),
        upload.FileCheckRequest(
            hash=hashlib.sha256(env.source).hexdigest(),
            size=len(env.source),
            name="photo.tiff",
            mime_type="image/tiff",
        ),
        SimpleNamespace(sub=owner, roles=[]),
    )


async def test_original_tiff_hash_reuses_stored_jpeg_without_retranscoding(env, monkeypatch):
    first = await send(env)
    row = env.records.rows[0]
    assert row["hash"] == hashlib.sha256(env.storage.uploaded[0]["data"]).hexdigest()
    assert row.get("source_hashes") == [hashlib.sha256(env.source).hexdigest()]
    result = await check(env)
    assert result["exists"] is True
    assert result["key"] == first["key"]
    assert result["mime_type"] == "image/jpeg"
    assert result["size"] == len(env.storage.uploaded[0]["data"])
    assert await check(env, owner="owner-b") == {"exists": False}
    monkeypatch.setattr(
        upload, "_prepare_spooled_image", AsyncMock(side_effect=AssertionError("retranscoded"))
    )
    repeated = await send(env)
    assert repeated["key"] == first["key"]
    assert repeated["exists"] is True
    assert len(env.storage.uploaded) == 1


async def test_legacy_canonical_record_learns_source_hash_after_verified_reupload(env):
    first = await send(env)
    env.records.rows[0].pop("source_hashes", None)
    assert await check(env) == {"exists": False}
    repeated = await send(env)
    assert repeated["key"] == first["key"]
    assert len(env.storage.uploaded) == 1
    assert (await check(env))["exists"] is True


async def test_racing_canonical_upload_teaches_winner_verified_source_hash(env):
    env.records.race = True
    result = await send(env)
    assert result["key"] == "image/owner-a/race-winner.jpg"
    assert (await check(env))["key"] == result["key"]
    env.storage.delete_file.assert_awaited_once_with(env.storage.uploaded[0]["key"])


async def test_source_alias_for_missing_object_deletes_canonical_record(env):
    await send(env)
    env.storage.file_exists.return_value = False
    assert await check(env) == {"exists": False}
    assert env.records.rows == []


async def test_source_alias_does_not_revive_tombstoned_record(env):
    await send(env)
    env.records.rows[0]["deleting_at"] = "reserved"
    assert await check(env) == {"exists": False}
    assert len(env.records.rows) == 1


async def test_unverified_check_hash_cannot_teach_an_alias(env):
    await send(env)
    env.records.rows[0].pop("source_hashes", None)
    assert await check(env) == {"exists": False}
    assert "source_hashes" not in env.records.rows[0]


async def test_legacy_raw_tiff_hash_still_transcodes_instead_of_reusing_unsafe_bytes(env):
    env.records.rows.append(
        {
            "hash": hashlib.sha256(env.source).hexdigest(),
            "key": "image/owner-a/legacy.tiff",
            "uploaded_by": "owner-a",
            "name": "photo.tiff",
            "mime_type": "image/tiff",
            "size": len(env.source),
            "category": "image",
        }
    )
    result = await send(env)
    assert result["mime_type"] == "image/jpeg"
    assert result["key"].endswith(".jpg")
    assert len(env.storage.uploaded) == 1


def large_image(fmt="JPEG"):
    import io

    from PIL import Image

    output = io.BytesIO()
    Image.effect_noise((2200, 1200), 100).convert("RGB").save(output, format=fmt, quality=98)
    return output.getvalue()


@pytest.mark.parametrize(
    "fmt,mime,extension", [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png")]
)
async def test_cloud_compresses_large_safe_images_and_retains_source_dedup(
    env, fmt, mime, extension
):
    import io

    from PIL import Image

    env.source = large_image(fmt)
    assert len(env.source) > 200 * 1024
    result = await upload.upload_file(
        _fake_request(), _TranscodeUpload(f"large.{extension}", mime, env.source), env.user
    )
    stored = env.storage.uploaded[0]
    with Image.open(io.BytesIO(stored["data"])) as image:
        assert max(image.size) <= 1920
        assert image.format == fmt
    assert result["size"] < len(env.source)
    assert env.records.rows[0]["source_hashes"] == [hashlib.sha256(env.source).hexdigest()]
    assert (await check(env))["key"] == result["key"]


async def test_cloud_image_input_can_exceed_final_limit_but_stored_image_cannot(env, monkeypatch):
    env.source = _tiff_bytes() + b"\0" * (1200 * 1024)
    monkeypatch.setattr(
        upload,
        "resolve_upload_limits",
        AsyncMock(return_value={"image": 1, "video": 1, "audio": 1, "document": 1}),
    )
    request = _fake_request()
    request.headers["content-length"] = str(len(env.source) + 512)
    result = await upload.upload_file(
        request, _TranscodeUpload("large.tiff", "image/tiff", env.source), env.user
    )
    assert result["size"] < 1024 * 1024
    assert result["mime_type"] == "image/jpeg"


async def test_multipart_overhead_at_image_input_ceiling_is_not_file_bytes(env, monkeypatch):
    env.source = _tiff_bytes()
    env.source += b"\0" * (2 * 1024 * 1024 - len(env.source))
    monkeypatch.setattr(
        upload,
        "resolve_upload_limits",
        AsyncMock(return_value={"image": 1, "video": 1, "audio": 1, "document": 1}),
    )
    request = _fake_request()
    request.headers["content-length"] = str(len(env.source) + 512)
    result = await upload.upload_file(
        request, _TranscodeUpload("large.tiff", "image/tiff", env.source), env.user
    )
    assert result["size"] < 1024 * 1024


async def test_cloud_processing_does_not_reuse_unprocessed_legacy_jpeg(env):
    import io

    from PIL import Image

    env.source = large_image()
    env.records.rows.append(
        {
            "hash": hashlib.sha256(env.source).hexdigest(),
            "key": "image/owner-a/legacy.jpg",
            "uploaded_by": "owner-a",
            "name": "large.jpg",
            "mime_type": "image/jpeg",
            "size": len(env.source),
            "category": "image",
        }
    )
    result = await upload.upload_file(
        _fake_request(), _TranscodeUpload("large.jpg", "image/jpeg", env.source), env.user
    )
    assert result["key"] != "image/owner-a/legacy.jpg"
    with Image.open(io.BytesIO(env.storage.uploaded[0]["data"])) as image:
        assert max(image.size) <= 1920


async def test_cloud_processing_reports_decode_failures_instead_of_skipping_compression(env):
    from src.kernel.errors import AppError

    with pytest.raises(AppError) as error:
        await upload.upload_file(
            _fake_request(),
            _TranscodeUpload("broken.jpg", "image/jpeg", b"x" * (201 * 1024)),
            env.user,
        )
    assert error.value.error_code.code == "image_transcode_failed"
    assert env.storage.uploaded == []


async def test_hash_check_cannot_bypass_cloud_processing_for_legacy_unprocessed_raster(env):
    env.source = large_image()
    env.records.rows.append(
        {
            "hash": hashlib.sha256(env.source).hexdigest(),
            "key": "image/owner-a/legacy.jpg",
            "uploaded_by": "owner-a",
            "name": "large.jpg",
            "mime_type": "image/jpeg",
            "size": len(env.source),
            "category": "image",
        }
    )
    result = await upload.check_file_exists(
        _fake_request(),
        upload.FileCheckRequest(
            hash=hashlib.sha256(env.source).hexdigest(),
            size=len(env.source),
            name="large.jpg",
            mime_type="image/jpeg",
        ),
        env.user,
    )
    assert result == {"exists": False}


async def test_prepared_unchanged_image_records_verified_identity_and_skips_repeat_processing(
    env, monkeypatch
):
    env.source = large_image()
    monkeypatch.setattr(
        upload_image,
        "prepare_upload_image_bytes",
        lambda content, mime_type, **_: (content, mime_type),
    )
    first = await upload.upload_file(
        _fake_request(), _TranscodeUpload("large.jpg", "image/jpeg", env.source), env.user
    )
    assert env.records.rows[0].get("source_hashes") == [hashlib.sha256(env.source).hexdigest()]
    assert (await check(env))["key"] == first["key"]
    monkeypatch.setattr(
        upload, "_prepare_spooled_image", AsyncMock(side_effect=AssertionError("reprocessed"))
    )
    repeated = await upload.upload_file(
        _fake_request(), _TranscodeUpload("large.jpg", "image/jpeg", env.source), env.user
    )
    assert repeated["key"] == first["key"]
    assert repeated["exists"] is True


async def test_processed_source_alias_wins_over_legacy_raw_canonical_row(env):
    env.source = large_image()
    env.records.rows.append(
        {
            "hash": hashlib.sha256(env.source).hexdigest(),
            "key": "image/owner-a/legacy.jpg",
            "uploaded_by": "owner-a",
            "name": "large.jpg",
            "mime_type": "image/jpeg",
            "size": len(env.source),
            "category": "image",
        }
    )
    processed = await upload.upload_file(
        _fake_request(), _TranscodeUpload("large.jpg", "image/jpeg", env.source), env.user
    )
    result = await check(env)
    assert result["key"] == processed["key"]
    assert result["key"] != "image/owner-a/legacy.jpg"


async def test_source_alias_reuse_respects_current_final_role_limit(env, monkeypatch):
    env.records.rows.append(
        {
            "hash": "b" * 64,
            "source_hashes": [hashlib.sha256(env.source).hexdigest()],
            "key": "image/owner-a/old-large.jpg",
            "uploaded_by": "owner-a",
            "name": "photo.tiff",
            "mime_type": "image/jpeg",
            "size": 2 * 1024 * 1024,
            "category": "image",
        }
    )
    monkeypatch.setattr(
        upload,
        "resolve_upload_limits",
        AsyncMock(return_value={"image": 1, "video": 1, "audio": 1, "document": 1}),
    )
    result = await send(env)
    assert result["size"] <= 1024 * 1024
    assert result["key"] != "image/owner-a/old-large.jpg"


async def test_hash_check_rejects_prepared_alias_above_current_role_final_limit(env, monkeypatch):
    env.records.rows.append(
        {
            "hash": "b" * 64,
            "source_hashes": [hashlib.sha256(env.source).hexdigest()],
            "key": "image/owner-a/old-large.jpg",
            "uploaded_by": "owner-a",
            "name": "photo.tiff",
            "mime_type": "image/jpeg",
            "size": 2 * 1024 * 1024,
            "category": "image",
        }
    )
    monkeypatch.setattr(
        upload,
        "resolve_upload_limits",
        AsyncMock(return_value={"image": 1, "video": 1, "audio": 1, "document": 1}),
    )
    assert await check(env) == {"exists": False}
