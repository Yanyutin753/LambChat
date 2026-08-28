"""文件封面缩略图（?cover=1）行为测试。

设计目标：文件库 16:9 封面只加载预览小图，不下载原文件——
S3/阿里云走「预签名 URL + x-oss-process」302 重定向（图片裁剪 /
视频首帧），本地存储用 Pillow 现场缩放，不支持的一律 404 让前端
回退到生成式封面。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes import upload


def _fake_request() -> SimpleNamespace:
    return SimpleNamespace(
        base_url="http://testserver/",
        headers={"host": "testserver"},
        url=SimpleNamespace(scheme="http"),
    )


class _FakeS3Storage:
    """阿里云 OSS 假后端：记录 presigned 调用参数。"""

    is_local = False

    def __init__(self, provider: str = "aliyun") -> None:
        self.presigned_calls: list[dict] = []
        config = SimpleNamespace(provider=provider, public_bucket=False)
        self._config = config

    async def file_exists(self, key: str) -> bool:
        return True

    async def get_presigned_url(
        self, key: str, expires: int = 3600, process: str | None = None
    ) -> str:
        self.presigned_calls.append({"key": key, "expires": expires, "process": process})
        return f"https://signed.example/{key}?sig=1"


@pytest.mark.asyncio
async def test_cover_redirects_to_processed_presigned_url_for_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    resp = await upload.get_file_proxy("revealed_files/hero.jpg", _fake_request(), cover=True)

    assert resp.status_code in (302, 307)
    assert storage.presigned_calls[0]["process"] == ("image/resize,m_fill,w_560,h_315")
    # 封面签名有效期应远大于普通 300 秒，便于浏览器/CDN 缓存
    assert storage.presigned_calls[0]["expires"] >= 86400
    assert "signed.example" in resp.headers["location"]


@pytest.mark.asyncio
async def test_cover_video_uses_requested_timestamp_defaulting_to_1s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    await upload.get_file_proxy("revealed_files/clip.mp4", _fake_request(), cover=True)
    await upload.get_file_proxy("revealed_files/clip.mp4", _fake_request(), cover=True, t=0)

    assert (
        "video/snapshot,t_1000,f_jpg,w_560,h_315,m_fast" == (storage.presigned_calls[0]["process"])
    )
    assert "video/snapshot,t_0,f_jpg,w_560,h_315,m_fast" == (storage.presigned_calls[1]["process"])


@pytest.mark.asyncio
async def test_cover_returns_404_for_unsupported_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    for key in ("a/b/archive.zip", "a/b/anim.gif", "a/b/icon.svg"):
        with pytest.raises(upload.HTTPException) as exc:
            await upload.get_file_proxy(key, _fake_request(), cover=True)
        assert exc.value.status_code == 404

    assert storage.presigned_calls == []


@pytest.mark.asyncio
async def test_cover_skips_processing_for_non_aliyun_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage(provider="minio")
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    with pytest.raises(upload.HTTPException) as exc:
        await upload.get_file_proxy("a/b/hero.jpg", _fake_request(), cover=True)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cover_serves_local_files_resized_by_pillow(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from PIL import Image

    src = tmp_path / "hero.jpg"
    Image.new("RGB", (640, 400), (200, 120, 60)).save(src, format="JPEG")

    class _FakeLocalStorage:
        is_local = True
        _config = SimpleNamespace(public_bucket=False)

        def get_file_path(self, key: str):
            assert key == "revealed_files/hero.jpg"
            return src

        async def file_exists(self, key: str) -> bool:  # pragma: no cover
            return True

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(_FakeLocalStorage()))

    resp = await upload.get_file_proxy("revealed_files/hero.jpg", _fake_request(), cover=True)

    assert resp.status_code == 200
    assert resp.media_type == "image/jpeg"
    import io

    from PIL import Image as _Img

    thumb = _Img.open(io.BytesIO(resp.body))
    assert thumb.size == (560, 315)


def _async_of(value):
    async def _factory():
        return value

    return _factory


@pytest.mark.asyncio
async def test_cover_signature_expiry_is_day_aligned_and_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    await upload.get_file_proxy("a/b/hero.jpg", _fake_request(), cover=True)
    await upload.get_file_proxy("a/b/hero.jpg", _fake_request(), cover=True)

    expires = [c["expires"] for c in storage.presigned_calls]
    # Same day → identical signed URL → browser/CDN disk-caches the thumb
    assert expires[0] == expires[1]
    assert expires[0] % 86400 == 0
    assert expires[0] >= 86400
