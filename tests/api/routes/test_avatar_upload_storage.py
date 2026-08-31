from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes import upload as upload_route
from src.kernel.errors import AppError


class _ChunkedUpload:
    filename = "avatar.png"
    content_type = "image/png"

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, size: int = -1) -> bytes:
        del size
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _BlockingOnlySpooledFile:
    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs
        self.data = bytearray()
        self.position = 0
        self.closed = False

    def write(self, chunk: bytes) -> int:
        if not getattr(upload_route, "_inside_fake_blocking_io", False):
            raise AssertionError("spooled writes must run in blocking IO executor")
        self.data[self.position : self.position + len(chunk)] = chunk
        self.position += len(chunk)
        return len(chunk)

    def read(self, size: int = -1) -> bytes:
        if not getattr(upload_route, "_inside_fake_blocking_io", False):
            raise AssertionError("spooled reads must run in blocking IO executor")
        if size < 0:
            size = len(self.data) - self.position
        chunk = bytes(self.data[self.position : self.position + size])
        self.position += len(chunk)
        return chunk

    def seek(self, position: int) -> int:
        if not getattr(upload_route, "_inside_fake_blocking_io", False):
            raise AssertionError("spooled seeks must run in blocking IO executor")
        self.position = position
        return position

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_upload_avatar_stores_object_url_without_base64(monkeypatch: pytest.MonkeyPatch):
    stored_update = {}
    uploaded = {}

    class _FakeStorage:
        async def delete_file(self, key: str):
            del key
            raise AssertionError("avatar upload without previous avatar should not delete files")

        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str,
            *,
            skip_size_limit: bool = False,
        ):
            uploaded.update(
                {
                    "data": file.read(),
                    "folder": folder,
                    "filename": filename,
                    "content_type": content_type,
                    "skip_size_limit": skip_size_limit,
                }
            )
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                url=f"https://cdn.example.com/{folder}/{filename}",
                size=len(uploaded["data"]),
                content_type=content_type,
            )

        async def upload_bytes(self, *args, **kwargs):
            raise AssertionError("avatar upload should not base64/upload bytes")

    class _FakeUserStorage:
        async def get_by_id(self, user_id):
            del user_id
            return None

        async def update(self, user_id, update):
            stored_update["user_id"] = user_id
            stored_update["avatar_url"] = update.avatar_url
            return None

    async def _get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(upload_route, "get_or_init_storage", _get_or_init_storage)
    monkeypatch.setattr("src.infra.user.storage.UserStorage", lambda: _FakeUserStorage())

    result = await upload_route.upload_avatar(
        file=_ChunkedUpload([b"\x89PNG\r\n\x1a\n", b"image-data", b""]),
        current_user=SimpleNamespace(sub="user-1"),
    )

    assert result == {
        "url": "https://cdn.example.com/avatars/user-1/avatar.png",
        "size": 18,
        "content_type": "image/png",
    }
    assert uploaded == {
        "data": b"\x89PNG\r\n\x1a\nimage-data",
        "folder": "avatars/user-1",
        "filename": "avatar.png",
        "content_type": "image/png",
        "skip_size_limit": True,
    }
    assert stored_update == {
        "user_id": "user-1",
        "avatar_url": "https://cdn.example.com/avatars/user-1/avatar.png",
    }
    assert not result["url"].startswith("data:")


@pytest.mark.asyncio
async def test_upload_avatar_offloads_spooled_header_probe(monkeypatch: pytest.MonkeyPatch):
    uploaded = {}

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str,
            *,
            skip_size_limit: bool = False,
        ):
            data = await fake_run_blocking_io(file.read)
            uploaded.update(
                {
                    "data": data,
                    "folder": folder,
                    "filename": filename,
                    "content_type": content_type,
                    "skip_size_limit": skip_size_limit,
                }
            )
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                url=f"https://cdn.example.com/{folder}/{filename}",
                size=len(uploaded["data"]),
                content_type=content_type,
            )

    class _FakeUserStorage:
        async def get_by_id(self, user_id):
            del user_id
            return None

        async def update(self, user_id, update):
            del user_id, update
            return None

    async def _get_or_init_storage():
        return _FakeStorage()

    async def fake_run_blocking_io(func, /, *args, **kwargs):
        monkeypatch.setattr(upload_route, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(upload_route, "_inside_fake_blocking_io", False, raising=False)

    monkeypatch.setattr(upload_route, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(upload_route, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(upload_route, "_inside_fake_blocking_io", False, raising=False)
    monkeypatch.setattr(upload_route, "get_or_init_storage", _get_or_init_storage)
    monkeypatch.setattr("src.infra.user.storage.UserStorage", lambda: _FakeUserStorage())

    result = await upload_route.upload_avatar(
        file=_ChunkedUpload([b"\x89PNG\r\n\x1a\n", b"image-data", b""]),
        current_user=SimpleNamespace(sub="user-1"),
    )

    assert result["content_type"] == "image/png"
    assert uploaded["data"] == b"\x89PNG\r\n\x1a\nimage-data"


@pytest.mark.asyncio
async def test_upload_avatar_deletes_previous_avatar_object_after_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []
    updates: list[str | None] = []

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str,
            *,
            skip_size_limit: bool = False,
        ):
            del file, content_type, skip_size_limit
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                url=f"https://cdn.example.com/{folder}/{filename}",
                size=18,
            )

        async def delete_file(self, key: str):
            deleted.append(key)
            return True

    class _FakeUserStorage:
        async def get_by_id(self, user_id):
            assert user_id == "user-1"
            return SimpleNamespace(
                avatar_url="https://cdn.example.com/avatars/user-1/old-avatar.png"
            )

        async def update(self, user_id, update):
            assert user_id == "user-1"
            updates.append(update.avatar_url)
            return None

    async def _get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(upload_route, "get_or_init_storage", _get_or_init_storage)
    monkeypatch.setattr("src.infra.user.storage.UserStorage", lambda: _FakeUserStorage())

    await upload_route.upload_avatar(
        file=_ChunkedUpload([b"\x89PNG\r\n\x1a\n", b"image-data", b""]),
        current_user=SimpleNamespace(sub="user-1"),
    )

    assert updates == ["https://cdn.example.com/avatars/user-1/avatar.png"]
    assert deleted == ["avatars/user-1/old-avatar.png"]


@pytest.mark.asyncio
async def test_delete_avatar_deletes_previous_avatar_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []
    updates: list[str | None] = []

    class _FakeStorage:
        async def delete_file(self, key: str):
            deleted.append(key)
            return True

    class _FakeUserStorage:
        async def get_by_id(self, user_id):
            assert user_id == "user-1"
            return SimpleNamespace(avatar_url="/api/upload/file/avatars/user-1/avatar.png")

        async def update(self, user_id, update):
            assert user_id == "user-1"
            updates.append(update.avatar_url)
            return None

    async def _get_or_init_storage():
        return _FakeStorage()

    monkeypatch.setattr(upload_route, "get_or_init_storage", _get_or_init_storage)
    monkeypatch.setattr("src.infra.user.storage.UserStorage", lambda: _FakeUserStorage())

    result = await upload_route.delete_avatar(current_user=SimpleNamespace(sub="user-1"))

    assert result == {"deleted": True}
    assert updates == [None]
    assert deleted == ["avatars/user-1/avatar.png"]


@pytest.mark.asyncio
async def test_upload_avatar_rejects_bad_extension_before_reading_file() -> None:
    upload = _ChunkedUpload([b"should-not-read"])
    upload.filename = "avatar.txt"

    with pytest.raises(AppError) as exc_info:
        await upload_route.upload_avatar(
            file=upload,
            current_user=SimpleNamespace(sub="user-1"),
        )

    assert exc_info.value.error_code.code == "file_type_not_allowed"
    assert exc_info.value.http_status == 400
    assert upload._chunks == [b"should-not-read"]
