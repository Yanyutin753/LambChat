"""docx 封面转换失败链路：原始 XML 兜底、失败负缓存与日志保真。

生产背景（#1163）：markitdown/mammoth 对部分 docx（WPS 等生成器）结构性
100% 失败，用户重试反复下载+转换+打 ERROR 刷屏；且 "File conversion
failed after 1 attempts" 的底层原因在消息第二行，日志采集按行切割后丢失。
"""

import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import upload, upload_cover
from src.api.routes.upload_content_cover import preview_text
from src.kernel.errors import AppError


@pytest.fixture(autouse=True)
def _owned_file_records(monkeypatch: pytest.MonkeyPatch) -> None:
    records = SimpleNamespace(
        is_private_key=AsyncMock(return_value=False),
        find_by_key=AsyncMock(return_value={"uploaded_by": "owner-a"}),
    )
    monkeypatch.setattr("src.infra.upload.access.get_file_record_storage", lambda: records)


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


def _make_docx_bytes(*, with_document: bool = True) -> bytes:
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        if with_document:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Fallback word report</w:t></w:r></w:p></w:body></w:document>',
            )
    return data.getvalue()


def _break_markitdown(monkeypatch: pytest.MonkeyPatch) -> None:
    import markitdown

    def _boom(self, *args, **kwargs):
        raise RuntimeError("DocxConverter cannot parse this structure")

    monkeypatch.setattr(markitdown.MarkItDown, "convert_stream", _boom)


def test_docx_markitdown_failure_falls_back_to_raw_document_xml(monkeypatch):
    _break_markitdown(monkeypatch)
    text = preview_text(_make_docx_bytes(), "docx")
    assert "Fallback word report" in text


def test_docx_fallback_failure_reraises_original_error(monkeypatch):
    _break_markitdown(monkeypatch)
    with pytest.raises(RuntimeError, match="DocxConverter cannot parse"):
        preview_text(_make_docx_bytes(with_document=False), "docx")


class _FakeStorage:
    """Stateful fake: uploaded objects become visible to file_exists."""

    is_local = False

    def __init__(self, payload: bytes) -> None:
        self._config = SimpleNamespace(provider="minio", public_bucket=False)
        self._payload = payload
        self.objects: dict[str, bytes] = {}
        self.downloaded: list[str] = []

    async def file_exists(self, key: str) -> bool:
        return key in self.objects

    async def get_size(self, key: str) -> int | None:
        return len(self._payload)

    async def download_file(self, key: str) -> bytes:
        self.downloaded.append(key)
        return self._payload

    async def upload_to_key(self, data: bytes, key: str, content_type=None, **kwargs) -> None:
        self.objects[key] = data


_OWNER = SimpleNamespace(sub="owner-a", permissions=["file:read"])
_MARKER = "covers/560x315/revealed_files/notes.docx.failed"


@pytest.mark.asyncio
async def test_render_failure_writes_marker_and_repeat_hits_404_without_redownload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(_make_docx_bytes())

    def _broken_render(data: bytes, ext: str) -> bytes:
        raise ValueError("File conversion failed after 1 attempts:\n - DocxConverter threw X")

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr("src.api.routes.upload_content_cover.render_content_cover", _broken_render)

    with pytest.raises(AppError) as first:
        await upload.get_file_proxy(
            "revealed_files/notes.docx", _fake_request(), cover=True, current_user=_OWNER
        )
    assert first.value.error_code.code == "cover_render_failed"

    assert _MARKER in storage.objects

    with pytest.raises(AppError) as second:
        await upload.get_file_proxy(
            "revealed_files/notes.docx", _fake_request(), cover=True, current_user=_OWNER
        )
    assert second.value.error_code.code == "cover_thumbnail_not_available"
    assert second.value.http_status == 404
    assert storage.downloaded == ["revealed_files/notes.docx"]


@pytest.mark.asyncio
async def test_render_failure_log_keeps_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    storage = _FakeStorage(_make_docx_bytes())

    def _broken_render(data: bytes, ext: str) -> bytes:
        raise ValueError(
            "File conversion failed after 1 attempts:\n - DocxConverter threw X with message: real cause"
        )

    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr("src.api.routes.upload_content_cover.render_content_cover", _broken_render)

    with caplog.at_level("ERROR"):
        with pytest.raises(AppError):
            await upload.get_file_proxy(
                "revealed_files/notes.docx", _fake_request(), cover=True, current_user=_OWNER
            )

    records = [r for r in caplog.records if "Failed to render" in r.message]
    assert records, "expected a render failure error log"
    assert records[0].exc_info, "expected the traceback to be attached to the log record"
    assert "real cause" in records[0].getMessage()


@pytest.mark.asyncio
async def test_download_failure_writes_no_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = _FakeStorage(_make_docx_bytes())

    async def _download_error(key: str) -> bytes:
        storage.downloaded.append(key)
        raise OSError("transient network error")

    storage.download_file = _download_error
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))

    with pytest.raises(AppError) as exc:
        await upload.get_file_proxy(
            "revealed_files/notes.docx", _fake_request(), cover=True, current_user=_OWNER
        )
    assert exc.value.error_code.code == "file_url_failed"
    assert not [key for key in storage.objects if key.endswith(".failed")]


def _async_of(value):
    async def _factory():
        return value

    return _factory
