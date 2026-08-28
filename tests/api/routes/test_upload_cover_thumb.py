"""文件封面缩略图（?cover=1）行为测试。

设计目标：文件库 16:9 封面只加载预览小图，不下载原文件——
S3/阿里云走「预签名 URL + x-oss-process」302 重定向（图片裁剪 /
视频首帧），本地存储用 Pillow 现场缩放，不支持的一律 404 让前端
回退到生成式封面。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from src.api.routes import upload, upload_cover
from src.api.routes.upload_cover import render_sheet_cover


@pytest.fixture(autouse=True)
def _reset_cover_concurrency_state():
    upload_cover._render_inflight.clear()
    upload_cover._render_sems.clear()
    yield
    upload_cover._render_inflight.clear()
    upload_cover._render_sems.clear()


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

    async def get_cover_presigned_url(
        self, key: str, expires_at: int, process: str | None = None
    ) -> str:
        self.presigned_calls.append({"key": key, "expires": expires_at, "process": process})
        return f"https://signed.example/{key}?Expires={expires_at}&sig=1"


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
    import time as _t

    # Absolute expiry within the next two days — NOT a relative offset that
    # oss2 would stack on top of now (that bug produced year-2083 URLs)
    assert _t.time() < expires[0] <= _t.time() + 2 * 86400


def _make_pdf_bytes() -> bytes:
    import io

    from PIL import ImageDraw

    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([90, 120, 700, 150], fill=(30, 30, 30))
    for i, y in enumerate([220, 260, 300, 340, 380]):
        d.rectangle([90, y, 1150 - i * 120, y + 14], fill=(150, 150, 150))
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


class _FakePdfStorage:
    """Aliyun-style storage that renders a real cached thumbnail."""

    is_local = False
    _config = SimpleNamespace(provider="aliyun", public_bucket=False)

    def __init__(
        self,
        cached: bool = False,
        size: int | None = 1000,
        payload: bytes | None = None,
    ) -> None:
        self.presigned_calls: list[dict] = []
        self.uploads: list[str] = []
        self.downloaded: list[str] = []
        self._cached = cached
        self._size = size
        self._payload = payload

    async def file_exists(self, key: str) -> bool:
        return self._cached if key.startswith("covers/") else True

    async def get_size(self, key: str) -> int | None:
        return self._size

    async def download_file(self, key: str) -> bytes:
        self.downloaded.append(key)
        return self._payload if self._payload is not None else _make_pdf_bytes()

    async def upload_to_key(self, data: bytes, key: str, content_type=None, **kwargs) -> None:
        self.uploads.append(key)

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


@pytest.mark.asyncio
async def test_cover_pdf_renders_first_page_and_caches_beside_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakePdfStorage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    resp = await upload.get_file_proxy("revealed_files/report.pdf", _fake_request(), cover=True)

    assert resp.status_code in (302, 307)
    assert storage.downloaded == ["revealed_files/report.pdf"]
    assert storage.uploads == ["covers/560x315/revealed_files/report.pdf.jpg"]
    # Redirect points at the cached thumbnail, unsigned process
    assert storage.presigned_calls[0]["key"] == ("covers/560x315/revealed_files/report.pdf.jpg")
    assert storage.presigned_calls[0]["process"] is None


@pytest.mark.asyncio
async def test_cover_pdf_serves_cached_thumbnail_without_re_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakePdfStorage(cached=True)
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    resp = await upload.get_file_proxy("revealed_files/report.pdf", _fake_request(), cover=True)

    assert resp.status_code in (302, 307)
    assert storage.downloaded == []
    assert storage.uploads == []


@pytest.mark.asyncio
async def test_cover_pdf_non_aliyun_provider_404s_without_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 Aliyun 后端不支持绝对过期签名，必须 404 兜底而非每次重下载重渲染。"""
    storage = _FakePdfStorage()
    storage._config = SimpleNamespace(provider="minio", public_bucket=False)
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    with pytest.raises(upload.HTTPException) as exc:
        await upload.get_file_proxy("revealed_files/report.pdf", _fake_request(), cover=True)
    assert exc.value.status_code == 404
    assert storage.downloaded == []
    assert storage.uploads == []
    assert storage.presigned_calls == []


@pytest.mark.asyncio
async def test_cover_pdf_skips_oversized_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakePdfStorage(size=80 * 1024 * 1024)
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    with pytest.raises(upload.HTTPException) as exc:
        await upload.get_file_proxy("revealed_files/huge.pdf", _fake_request(), cover=True)
    assert exc.value.status_code == 404
    assert storage.downloaded == []


@pytest.mark.asyncio
async def test_cover_pdf_local_storage_renders_real_jpeg(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    src = tmp_path / "report.pdf"
    src.write_bytes(_make_pdf_bytes())

    class _FakeLocalStorage:
        is_local = True
        _config = SimpleNamespace(public_bucket=False)

        def get_file_path(self, key: str):
            return src

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(_FakeLocalStorage()))

    resp = await upload.get_file_proxy("revealed_files/report.pdf", _fake_request(), cover=True)

    assert resp.status_code == 200
    assert resp.media_type == "image/jpeg"
    import io

    cover = Image.open(io.BytesIO(resp.body))
    assert cover.size == (1120, 630)


# ── CJK font bootstrap ───────────────────────────────────────────────────


def test_ensure_cjk_fonts_copies_bundled_font_when_missing(tmp_path, monkeypatch):
    from src.api.routes import upload_cover as cover

    empty_scan = tmp_path / "scan-empty"
    empty_scan.mkdir()
    install_dir = tmp_path / "install"
    monkeypatch.setattr(cover, "_cjk_fonts_ensured", False)

    ok = cover.ensure_cjk_fonts_available(scan_dirs=[str(empty_scan)], install_dir=install_dir)

    assert ok is True
    installed = install_dir / "NotoSansCJK-Regular.ttc"
    assert installed.exists()
    assert installed.stat().st_size == cover._BUNDLED_CJK_FONT.stat().st_size


def test_ensure_cjk_fonts_noop_when_system_font_present(tmp_path, monkeypatch):
    from src.api.routes import upload_cover as cover

    scan = tmp_path / "scan"
    scan.mkdir()
    (scan / "NotoSansCJK-Bold.ttc").write_bytes(b"fake")
    install_dir = tmp_path / "install"
    monkeypatch.setattr(cover, "_cjk_fonts_ensured", False)

    ok = cover.ensure_cjk_fonts_available(scan_dirs=[str(scan)], install_dir=install_dir)

    assert ok is True
    assert not install_dir.exists()


def test_ensure_cjk_fonts_warns_when_not_writable(tmp_path, monkeypatch):
    from src.api.routes import upload_cover as cover

    empty_scan = tmp_path / "scan-empty"
    empty_scan.mkdir()
    blocked = tmp_path / "blocked"  # a FILE: mkdir will fail
    blocked.write_text("occupied")
    monkeypatch.setattr(cover, "_cjk_fonts_ensured", False)

    ok = cover.ensure_cjk_fonts_available(
        scan_dirs=[str(empty_scan)], install_dir=blocked / "fonts"
    )

    assert ok is False


def test_render_pdf_cover_renders_real_chinese_text():
    """End-to-end with the bundled CJK font: embedded-font PDF renders
    real glyphs on every system, regardless of installed fonts."""
    import io

    from src.api.routes.upload_cover import render_pdf_cover

    font = ImageFont.truetype(str(_bundled_font_path()), 30, index=0)
    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    draw.text((90, 200), "架构设计文档：中文渲染验证", font=font, fill=(20, 22, 28))
    draw.text((90, 280), "飞书风格文件封面 — 简约大气", font=font, fill=(60, 64, 74))
    buf = io.BytesIO()
    img.save(buf, format="PDF")

    out = render_pdf_cover(buf.getvalue())

    cover_img = Image.open(io.BytesIO(out))
    assert cover_img.size == (1120, 630)
    assert cover_img.mode == "RGB"
    # Real glyph rasterization produces a meaningfully sized JPEG; a tofu
    # failure still encodes boxes but embedded fonts make this deterministic.
    assert len(out) > 10000


def _bundled_font_path():
    from src.api.routes import upload_cover as cover

    return cover._BUNDLED_CJK_FONT


def test_render_pdf_cover_fills_canvas_without_letterbox():
    """A solid-color page must fill the whole 16:9 canvas — the old
    letterbox logic would leave white bars on A4 pages."""
    import io

    from src.api.routes.upload_cover import render_pdf_cover

    buf = io.BytesIO()
    Image.new("RGB", (595, 842), (40, 80, 160)).save(buf, format="PDF")

    out = render_pdf_cover(buf.getvalue())
    cover = Image.open(io.BytesIO(out))
    assert cover.size == (1120, 630)

    corners = [
        cover.getpixel((2, 2)),
        cover.getpixel((1117, 2)),
        cover.getpixel((2, 627)),
        cover.getpixel((1117, 627)),
    ]
    for r, g, b in corners:
        # Page blue, not letterbox white
        assert abs(r - 40) < 12 and abs(g - 80) < 12 and abs(b - 160) < 12


def _make_xlsx_bytes() -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["月份", "营收", "成本", "利润"])
    ws.append(["2026 Q1", "1280", "640", "640"])
    ws.append(["2026 Q2", "1542", "701", "841"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_cover_sheet_renders_real_rows_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakePdfStorage(payload=_make_xlsx_bytes())

    def _fake_render(data: bytes) -> bytes:
        assert data[:2] == b"PK"  # xlsx is a zip container
        return b"fake-sheet-jpeg"

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr("src.api.routes.upload_cover.render_sheet_cover", _fake_render)

    resp = await upload.get_file_proxy("revealed_files/report.xlsx", _fake_request(), cover=True)

    assert resp.status_code in (302, 307)
    assert storage.downloaded == ["revealed_files/report.xlsx"]
    assert storage.uploads == ["covers/560x315/revealed_files/report.xlsx.jpg"]


@pytest.mark.asyncio
async def test_cover_legacy_xls_falls_back_without_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakePdfStorage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    with pytest.raises(upload.HTTPException) as exc:
        await upload.get_file_proxy("revealed_files/old.xls", _fake_request(), cover=True)
    assert exc.value.status_code == 404
    assert storage.downloaded == []


def test_render_sheet_cover_draws_real_chinese_table():
    import io

    out = render_sheet_cover(_make_xlsx_bytes())

    cover = Image.open(io.BytesIO(out))
    assert cover.size == (1120, 630)
    # Real CJK cell text drawn with the bundled font produces a real table
    assert len(out) > 12000


# ── Concurrency protection ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_first_requests_render_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cache-stampede guard: N users hitting the same fresh PDF share one
    download+render instead of piling onto the shared blocking-io pool."""
    import asyncio
    import time as _time

    storage = _FakePdfStorage()

    def _slow_render(data: bytes) -> bytes:
        _time.sleep(0.15)
        return b"fake-jpeg"

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr("src.api.routes.upload_cover.render_pdf_cover", _slow_render)

    responses = await asyncio.gather(
        *[
            upload.get_file_proxy("revealed_files/report.pdf", _fake_request(), cover=True)
            for _ in range(4)
        ]
    )

    assert all(r.status_code in (302, 307) for r in responses)
    assert storage.downloaded == ["revealed_files/report.pdf"]
    assert storage.uploads == ["covers/560x315/revealed_files/report.pdf.jpg"]


@pytest.mark.asyncio
async def test_render_burst_degrades_to_404_instead_of_pool_starvation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the render slots are saturated, extra requests fall back with a
    fast 404 (client shows the paper cover) instead of queueing behind the
    shared blocking-io pool."""
    import asyncio
    import time as _time

    import src.api.routes.upload_cover as cover_mod

    storage = _FakePdfStorage()

    def _slow_render(data: bytes) -> bytes:
        _time.sleep(0.3)
        return b"fake-jpeg"

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr("src.api.routes.upload_cover.render_pdf_cover", _slow_render)
    monkeypatch.setattr(cover_mod, "_RENDER_ACQUIRE_TIMEOUT", 0.05)

    # Occupy both render slots with distinct keys
    first_two = [
        asyncio.create_task(
            upload.get_file_proxy(f"revealed_files/a{i}.pdf", _fake_request(), cover=True)
        )
        for i in range(2)
    ]
    await asyncio.sleep(0.05)

    with pytest.raises(upload.HTTPException) as exc:
        await upload.get_file_proxy("revealed_files/burst.pdf", _fake_request(), cover=True)
    assert exc.value.status_code == 404

    done = await asyncio.gather(*first_two)
    assert all(r.status_code in (302, 307) for r in done)
