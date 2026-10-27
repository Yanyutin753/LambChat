"""A cutover must prove the entire source, not just a listing's first page."""

import hashlib

import pytest

from src.infra.storage.s3.migration import verify_contents


class Objects:
    def __init__(self, objects):
        self.objects = objects
        self.read = []

    async def iter_keys(self):
        for key in self.objects:
            yield key

    async def download_stream(self, key, chunk_size=1024 * 1024):
        self.read.append(key)
        body = self.objects[key]
        for start in range(0, len(body), 3):
            yield body[start : start + 3]


async def test_missing_object_beyond_first_listing_page_blocks_cutover():
    objects = {f"file/{i}": b"original" for i in range(1002)}
    destination = dict(objects)
    del destination["file/1001"]
    with pytest.raises(ValueError, match="incomplete"):
        await verify_contents(Objects(objects), Objects(destination), {})


async def test_same_size_corruption_blocks_cutover():
    with pytest.raises(ValueError, match="checksum"):
        await verify_contents(Objects({"file": b"good"}), Objects({"file": b"evil"}), {})


async def test_all_original_objects_including_unindexed_skill_and_avatar_are_checked():
    objects = {"skills/user/a.bin": b"skill", "avatars/user/a.png": b"image"}
    result = await verify_contents(Objects(objects), Objects(objects), {})
    assert result == {"objects": 2, "bytes": 10}


async def test_missing_source_reference_requires_matching_original_hash():
    digest = hashlib.sha256(b"restored").hexdigest()
    assert await verify_contents(Objects({}), Objects({"old": b"restored"}), {"old": digest}) == {
        "objects": 1,
        "bytes": 8,
    }
    with pytest.raises(ValueError, match="checksum"):
        await verify_contents(Objects({}), Objects({"old": b"corrupt!"}), {"old": digest})
    with pytest.raises(ValueError, match="source"):
        await verify_contents(Objects({}), Objects({"old": b"restored"}), {"old": None})


async def test_storage_errors_never_count_as_empty_source():
    class Offline(Objects):
        async def iter_keys(self):
            raise ConnectionError("unavailable")
            yield

    with pytest.raises(ConnectionError):
        await verify_contents(Offline({}), Objects({}), {})


async def test_matching_copies_must_also_match_recorded_original_hash():
    original = hashlib.sha256(b"original").hexdigest()
    with pytest.raises(ValueError, match="checksum"):
        await verify_contents(
            Objects({"file": b"corrupt"}), Objects({"file": b"corrupt"}), {"file": original}
        )


@pytest.mark.parametrize("provider", ["aliyun", "minio", "local"])
async def test_backend_inventory_exhausts_all_pages(provider, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from src.infra.storage.s3.backends.aliyun import AliyunOssBackend
    from src.infra.storage.s3.backends.local import LocalStorageBackend
    from src.infra.storage.s3.backends.minio import MinioS3Backend
    from src.infra.storage.s3.types import S3Config, S3Provider

    names = [f"file-{i}" for i in range(1002)]
    config = S3Config(provider=S3Provider(provider), bucket_name="test", storage_path=str(tmp_path))
    if provider == "aliyun":
        backend = AliyunOssBackend(config)
        monkeypatch.setattr(backend, "_get_bucket", lambda: object())
        monkeypatch.setattr(
            "oss2.ObjectIteratorV2", lambda *a, **kw: (SimpleNamespace(key=n) for n in names)
        )
    elif provider == "minio":
        backend = MinioS3Backend(config)
        monkeypatch.setattr(
            backend,
            "_get_client",
            lambda: SimpleNamespace(
                list_objects=lambda *a, **kw: (SimpleNamespace(object_name=n) for n in names)
            ),
        )
    else:
        backend = LocalStorageBackend(config)
        for name in names:
            (tmp_path / name).write_bytes(b"original")
    assert {key async for key in backend.iter_keys()} == set(names)
