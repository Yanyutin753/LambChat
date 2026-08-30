"""对话消息缩略图（?thumb=1）行为测试。

设计目标：聊天气泡只加载等比小图，点击放大才取原图——
阿里云走「预签名 URL + x-oss-process m_lfit」302，本地存储用
Pillow 现场等比缩放，其余 S3 厂商（minio/AWS/腾讯…）下载原文件
用 Pillow 渲染一次并缓存到原文件旁边，后续请求直接吃缓存小图。
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image

from src.api.routes import upload
from src.kernel.errors import AppError


@pytest.fixture(autouse=True)
def _reset_thumb_concurrency_state():
    from src.api.routes import upload_thumb

    upload_thumb._thumb_inflight.clear()
    yield
    upload_thumb._thumb_inflight.clear()


def _fake_request() -> SimpleNamespace:
    return SimpleNamespace(
        base_url="http://testserver/",
        headers={"host": "testserver"},
        url=SimpleNamespace(scheme="http"),
    )


class _FakeS3Storage:
    """记录 presigned 调用参数的可配置假后端。"""

    is_local = False

    def __init__(self, provider: str = "aliyun") -> None:
        self.presigned_calls: list[dict] = []
        self._config = SimpleNamespace(provider=provider, public_bucket=False)

    async def file_exists(self, key: str) -> bool:
        return True

    async def get_presigned_url(
        self, key: str, expires: int = 3600, process: str | None = None
    ) -> str:
        self.presigned_calls.append({"key": key, "expires": expires, "process": process})
        return f"https://signed.example/{key}?sig=1"

    async def get_cover_presigned_url(
        self, key: str, expires_at: int, process: str | None = None
    ) -> str:
        self.presigned_calls.append({"key": key, "expires": expires_at, "process": process})
        return f"https://signed.example/{key}?Expires={expires_at}&sig=1"


def _async_of(value):
    async def _factory():
        return value

    return _factory


# ── Aliyun: x-oss-process 302 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thumb_redirects_to_lfit_presigned_url_on_aliyun(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    resp = await upload.get_file_proxy("revealed_files/hero.jpg", _fake_request(), thumb=True)

    assert resp.status_code in (302, 307)
    assert storage.presigned_calls[0]["process"] == "image/resize,m_lfit,w_560,h_560"
    assert storage.presigned_calls[0]["expires"] >= 86400
    assert storage.presigned_calls[0]["expires"] % 86400 == 0
    assert "signed.example" in resp.headers["location"]
    assert resp.headers["cache-control"] == "public, max-age=86400"


@pytest.mark.asyncio
async def test_thumb_signature_is_day_aligned_and_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    await upload.get_file_proxy("a/b/hero.jpg", _fake_request(), thumb=True)
    await upload.get_file_proxy("a/b/hero.jpg", _fake_request(), thumb=True)

    expires = [c["expires"] for c in storage.presigned_calls]
    assert expires[0] == expires[1]


@pytest.mark.asyncio
async def test_thumb_404s_for_unsupported_types_without_traffic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    for key in ("a/b/anim.gif", "a/b/icon.svg", "a/b/archive.zip", "a/b/clip.mp4"):
        with pytest.raises(AppError) as exc:
            await upload.get_file_proxy(key, _fake_request(), thumb=True)
        assert exc.value.error_code.code == "thumb_not_available"
        assert exc.value.http_status == 404

    assert storage.presigned_calls == []


# ── Local: Pillow 等比渲染 ────────────────────────────────────────────────


def _write_image(path, size: tuple[int, int], mode: str = "RGB") -> None:
    color = (200, 120, 60) if mode == "RGB" else (200, 120, 60, 0)
    Image.new(mode, size, color).save(path, format="PNG" if mode != "RGB" else "JPEG")


class _FakeLocalStorage:
    is_local = True
    _config = SimpleNamespace(public_bucket=False)

    def __init__(self, src) -> None:
        self._src = src

    def get_file_path(self, key: str):
        return self._src


@pytest.mark.asyncio
async def test_thumb_local_renders_aspect_fit_without_cropping(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    src = tmp_path / "hero.jpg"
    _write_image(src, (640, 400))

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(_FakeLocalStorage(src)))

    resp = await upload.get_file_proxy("revealed_files/hero.jpg", _fake_request(), thumb=True)

    assert resp.status_code == 200
    assert resp.media_type == "image/jpeg"
    assert resp.headers["cache-control"] == "public, max-age=86400"
    thumb = Image.open(io.BytesIO(resp.body))
    # m_lfit：等比缩放，整图可见（640x400 → 560x350）
    assert thumb.size == (560, 350)


@pytest.mark.asyncio
async def test_thumb_local_binds_both_dimensions_for_tall_images(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    src = tmp_path / "tall.jpg"
    _write_image(src, (400, 1600))

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(_FakeLocalStorage(src)))

    resp = await upload.get_file_proxy("revealed_files/tall.jpg", _fake_request(), thumb=True)

    thumb = Image.open(io.BytesIO(resp.body))
    assert thumb.size[1] == 560
    assert thumb.size[0] == 140


@pytest.mark.asyncio
async def test_thumb_local_composites_alpha_onto_white(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    src = tmp_path / "logo.png"
    _write_image(src, (300, 300), mode="RGBA")

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(_FakeLocalStorage(src)))

    resp = await upload.get_file_proxy("revealed_files/logo.png", _fake_request(), thumb=True)

    thumb = Image.open(io.BytesIO(resp.body))
    assert thumb.mode == "RGB"
    # 透明区域合成到白底，而不是 JPEG 转换的黑色
    r, g, b = thumb.getpixel((0, 0))
    assert r > 240 and g > 240 and b > 240


@pytest.mark.asyncio
async def test_thumb_local_missing_file_404s(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(
        upload,
        "get_or_init_storage",
        _async_of(_FakeLocalStorage(tmp_path / "nope.jpg")),
    )

    with pytest.raises(AppError) as exc:
        await upload.get_file_proxy("revealed_files/nope.jpg", _fake_request(), thumb=True)
    assert exc.value.error_code.code == "file_not_found"
    assert exc.value.http_status == 404


# ── 其他 S3 厂商：渲染一次 + 缓存到原文件旁边 ────────────────────────────


def _jpeg_bytes(size: tuple[int, int] = (1200, 900)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 60, 30)).save(buf, format="JPEG")
    return buf.getvalue()


class _FakeRenderStorage:
    """minio 式假后端：完整模拟 缓存检查→下载→渲染→写缓存。"""

    is_local = False

    def __init__(self, cached: bool = False, size: int | None = 500_000) -> None:
        self._cached = cached
        self._size = size
        self._config = SimpleNamespace(provider="minio", public_bucket=False)
        self.downloads: list[str] = []
        self.uploads: list[str] = []

    async def file_exists(self, key: str) -> bool:
        return self._cached if key.startswith("thumbs/") else True

    async def get_size(self, key: str) -> int | None:
        return self._size

    async def download_file(self, key: str) -> bytes:
        self.downloads.append(key)
        return _jpeg_bytes()

    async def upload_to_key(self, data: bytes, key: str, content_type=None, **kwargs) -> None:
        self.uploads.append(key)

    async def get_presigned_url(self, key, expires=3600, process=None) -> str:
        return f"https://signed.example/{key}?sig=1"


@pytest.mark.asyncio
async def test_thumb_non_aliyun_renders_and_caches_beside_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeRenderStorage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    resp = await upload.get_file_proxy("revealed_files/hero.jpg", _fake_request(), thumb=True)

    assert resp.status_code == 200
    assert resp.media_type == "image/jpeg"
    assert resp.headers["cache-control"] == "public, max-age=86400"
    assert storage.downloads == ["revealed_files/hero.jpg"]
    assert storage.uploads == ["thumbs/560/revealed_files/hero.jpg.jpg"]
    thumb = Image.open(io.BytesIO(resp.body))
    assert thumb.size == (560, 420)


@pytest.mark.asyncio
async def test_thumb_non_aliyun_serves_cache_without_re_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeRenderStorage(cached=True)
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    resp = await upload.get_file_proxy("revealed_files/hero.jpg", _fake_request(), thumb=True)

    assert resp.status_code == 200
    assert storage.downloads == ["thumbs/560/revealed_files/hero.jpg.jpg"]
    assert storage.uploads == []


@pytest.mark.asyncio
async def test_thumb_non_aliyun_skips_oversized_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeRenderStorage(size=80 * 1024 * 1024)
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    with pytest.raises(AppError) as exc:
        await upload.get_file_proxy("revealed_files/huge.jpg", _fake_request(), thumb=True)
    assert exc.value.error_code.code == "thumb_not_available"
    assert exc.value.http_status == 404
    assert storage.downloads == []


@pytest.mark.asyncio
async def test_thumb_concurrent_first_requests_render_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    storage = _FakeRenderStorage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    responses = await asyncio.gather(
        *[
            upload.get_file_proxy("revealed_files/hero.jpg", _fake_request(), thumb=True)
            for _ in range(4)
        ]
    )

    assert all(r.status_code == 200 for r in responses)
    assert storage.downloads == ["revealed_files/hero.jpg"]
    assert storage.uploads == ["thumbs/560/revealed_files/hero.jpg.jpg"]
