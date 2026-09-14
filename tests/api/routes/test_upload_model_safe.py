"""图片上传/读取的模型安全格式转码测试。

视觉模型（如 GLM）无法解码 TIFF/BMP/ICO 等格式（1210 图片输入格式/解析
错误），浏览器 canvas 也解不了 TIFF，前端压缩 worker 只能原样透传。后端
在两条路径上兜底：

- 上传时：非模型安全格式的图片转码为 JPEG 后再落存储（新文件全部安全）；
- 读取时：存量 ``image/…​.tiff`` 等 key 现场转码并缓存到原文件旁边
  （render-once，历史会话里的旧 URL 也能自愈）。
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image

from src.api.routes import upload
from src.kernel.errors import AppError


def _tiff_bytes(mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    color = (200, 120, 60) if mode == "RGB" else (200, 120, 60, 0)
    Image.new(mode, (40, 30), color).save(buf, format="TIFF")
    return buf.getvalue()


def _fake_request() -> SimpleNamespace:
    return SimpleNamespace(
        base_url="http://testserver/",
        headers={"host": "testserver"},
        url=SimpleNamespace(scheme="http"),
    )


def _async_of(value):
    async def _factory():
        return value

    return _factory


# ── 上传：TIFF 转码为 JPEG 后存储 ─────────────────────────────────────────


class _TranscodeUpload:
    def __init__(self, filename: str, content_type: str, payload: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._chunks = [payload, b""]

    async def read(self, _size: int) -> bytes:
        return self._chunks.pop(0)


class _RecordingRecords:
    def __init__(self) -> None:
        self.created: list[dict] = []

    async def find_by_hash(self, _file_hash: str, _uploaded_by: str):
        return None

    async def create(self, **kwargs):
        self.created.append(kwargs)

    async def delete_by_hash(self, _file_hash: str, _uploaded_by: str):
        return True

    async def refresh_owned_cleanup(self, _key: str, _uploaded_by: str) -> bool:
        return True


class _RecordingStorage:
    is_local = False
    _config = SimpleNamespace(public_bucket=False)

    def __init__(self) -> None:
        self.uploaded: list[dict] = []

    async def file_exists(self, _key: str) -> bool:
        return False

    async def upload_stream_to_key(self, *, file, key, content_type, **_kwargs):
        file.seek(0)
        self.uploaded.append({"key": key, "content_type": content_type, "data": file.read()})
        return SimpleNamespace(key=key)


@pytest.mark.asyncio
async def test_upload_transcodes_tiff_to_jpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _RecordingStorage()
    records = _RecordingRecords()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr(upload, "_file_record_storage", records)

    async def _limits(_roles):
        return {"image": 10, "video": 10, "audio": 10, "document": 10}

    monkeypatch.setattr(upload, "resolve_upload_limits", _limits)

    result = await upload.upload_file(
        request=SimpleNamespace(headers={}, base_url="http://testserver/"),
        file=_TranscodeUpload("photo.tiff", "image/tiff", _tiff_bytes()),
        current_user=SimpleNamespace(sub="owner-a", permissions=["file:upload"], roles=[]),
    )

    # 存储收到的是 JPEG
    assert len(storage.uploaded) == 1
    stored = storage.uploaded[0]
    assert stored["key"].startswith("image/owner-a/")
    assert stored["key"].endswith(".jpg")
    assert stored["content_type"] == "image/jpeg"
    with Image.open(io.BytesIO(stored["data"])) as image:
        assert image.format == "JPEG"
        assert image.size == (40, 30)

    # 记录与响应的 mime/类型一致
    assert records.created[0]["mime_type"] == "image/jpeg"
    assert records.created[0]["category"] == "image"
    assert result["mime_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_upload_transcode_failure_rejected_with_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _RecordingStorage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr(upload, "_file_record_storage", _RecordingRecords())

    async def _limits(_roles):
        return {"image": 10, "video": 10, "audio": 10, "document": 10}

    monkeypatch.setattr(upload, "resolve_upload_limits", _limits)

    with pytest.raises(AppError) as exc_info:
        await upload.upload_file(
            request=SimpleNamespace(headers={}, base_url="http://testserver/"),
            file=_TranscodeUpload("broken.tiff", "image/tiff", b"not-a-tiff"),
            current_user=SimpleNamespace(sub="owner-a", permissions=["file:upload"], roles=[]),
        )

    assert exc_info.value.error_code.code == "image_transcode_failed"
    assert exc_info.value.http_status == 400
    assert storage.uploaded == []


@pytest.mark.asyncio
async def test_upload_jpeg_passes_through_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (1, 2, 3)).save(buf, format="JPEG")
    original = buf.getvalue()

    storage = _RecordingStorage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr(upload, "_file_record_storage", _RecordingRecords())

    async def _limits(_roles):
        return {"image": 10, "video": 10, "audio": 10, "document": 10}

    monkeypatch.setattr(upload, "resolve_upload_limits", _limits)

    await upload.upload_file(
        request=SimpleNamespace(headers={}, base_url="http://testserver/"),
        file=_TranscodeUpload("photo.jpg", "image/jpeg", original),
        current_user=SimpleNamespace(sub="owner-a", permissions=["file:upload"], roles=[]),
    )

    assert len(storage.uploaded) == 1
    assert storage.uploaded[0]["key"].endswith(".jpg")
    assert storage.uploaded[0]["data"] == original


# ── 读取：存量 image/…​.tiff 自愈转码（render-once 缓存到原文件旁）─────────


@pytest.fixture(autouse=True)
def _reset_model_safe_concurrency_state():
    from src.api.routes import upload_model_safe

    upload_model_safe._model_safe_inflight.clear()
    yield
    upload_model_safe._model_safe_inflight.clear()


class _FakeSafeRenderStorage:
    """minio 式假后端：缓存检查→下载→转码→写缓存。"""

    is_local = False
    _config = SimpleNamespace(provider="minio", public_bucket=False)

    def __init__(self, cached: bool = False) -> None:
        self._cached = cached
        self.files: dict[str, bytes] = {"image/owner-a/legacy.tiff": _tiff_bytes()}
        self.downloads: list[str] = []
        self.uploads: list[str] = []

    async def file_exists(self, key: str) -> bool:
        if key.startswith("model-safe/"):
            return self._cached
        return key in self.files

    async def get_size(self, key: str) -> int | None:
        data = self.files.get(key)
        return len(data) if data else None

    async def download_file(self, key: str) -> bytes:
        self.downloads.append(key)
        return self.files[key]

    async def upload_to_key(self, data: bytes, key: str, content_type=None, **_kw) -> None:
        self.uploads.append(key)
        self.files[key] = data

    async def get_presigned_url(self, key, expires=3600, process=None) -> str:
        return f"https://signed.example/{key}?sig=1"


@pytest.mark.asyncio
async def test_get_file_transcodes_legacy_tiff_and_caches_beside_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeSafeRenderStorage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    resp = await upload.get_file_proxy("image/owner-a/legacy.tiff", _fake_request())

    assert resp.status_code == 200
    assert resp.media_type == "image/jpeg"
    assert storage.downloads == ["image/owner-a/legacy.tiff"]
    assert storage.uploads == ["model-safe/image/owner-a/legacy.tiff.jpg"]
    with Image.open(io.BytesIO(resp.body)) as image:
        assert image.format == "JPEG"
        assert image.size == (40, 30)


@pytest.mark.asyncio
async def test_get_file_serves_cached_transcode_without_re_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeSafeRenderStorage(cached=True)
    storage.files["model-safe/image/owner-a/legacy.tiff.jpg"] = b"cached-jpeg"
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    resp = await upload.get_file_proxy("image/owner-a/legacy.tiff", _fake_request())

    assert resp.status_code == 200
    assert resp.body == b"cached-jpeg"
    assert storage.downloads == ["model-safe/image/owner-a/legacy.tiff.jpg"]
    assert storage.uploads == []


@pytest.mark.asyncio
async def test_get_file_local_storage_transcodes_on_the_fly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    src = tmp_path / "legacy.tiff"
    src.write_bytes(_tiff_bytes())

    class _FakeLocal:
        is_local = True
        _config = SimpleNamespace(public_bucket=False)

        def get_file_path(self, _key: str):
            return src

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(_FakeLocal()))

    resp = await upload.get_file_proxy("image/owner-a/legacy.tiff", _fake_request())

    assert resp.status_code == 200
    assert resp.media_type == "image/jpeg"
    with Image.open(io.BytesIO(resp.body)) as image:
        assert image.format == "JPEG"


@pytest.mark.asyncio
async def test_get_file_safe_formats_and_documents_stay_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeSafeRenderStorage()
    storage.files["image/owner-a/fine.jpg"] = b"jpeg-bytes"
    storage.files["document/owner-a/scan.tiff"] = _tiff_bytes()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    # 安全格式：照旧走 302 presigned
    resp = await upload.get_file_proxy("image/owner-a/fine.jpg", _fake_request())
    assert resp.status_code == 302

    # document 前缀的 tiff 不转码（多页文档转 JPEG 会丢页，维持原样 302）
    resp = await upload.get_file_proxy("document/owner-a/scan.tiff", _fake_request())
    assert resp.status_code == 302

    assert storage.uploads == []
