"""?proxy=true 流式代理的 Content-Disposition 编码测试。

背景：OSS 直连不可达的客户端靠 ?proxy=true 兜底预览，而代理分支把
文件记录里的原始文件名（常含中文）直接拼进 HTTP 头，latin-1 编码
失败导致 500，前端只能报「从存储加载文件失败」。
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


def _async_of(value):
    async def _factory():
        return value

    return _factory


class _FakeS3Storage:
    """非本地存储假后端：只实现代理分支用到的接口。"""

    is_local = False

    def __init__(self, payload: bytes = b"PK\x05\x06fake-docx") -> None:
        self._payload = payload

    async def file_exists(self, key: str) -> bool:
        return True

    async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
        yield self._payload


class _FakeRecordStorage:
    def __init__(self, record: dict | None) -> None:
        self._record = record

    async def find_by_key(self, key: str, user_id: str | None = None) -> dict | None:
        return self._record


@pytest.mark.asyncio
async def test_proxy_stream_with_cjk_filename_builds_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中文文件名走 RFC 5987 的 filename*=utf-8''，头必须可 latin-1 编码。"""
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr(
        upload,
        "_file_record_storage",
        _FakeRecordStorage(
            {"name": "项目方案（终稿）.docx", "mime_type": None},
        ),
    )

    resp = await upload.get_file_proxy("document/u1/abc.docx", _fake_request(), proxy=True)

    assert resp.status_code == 200
    disposition = resp.headers["content-disposition"]
    # 构造阶段不再抛 UnicodeEncodeError，且值能安全编码进 HTTP 头
    disposition.encode("latin-1")
    assert "filename*=utf-8''" in disposition
    assert "%E9%A1%B9%E7%9B%AE" in disposition  # 「项目」的百分号编码


@pytest.mark.asyncio
async def test_proxy_stream_with_ascii_filename_keeps_plain_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr(
        upload,
        "_file_record_storage",
        _FakeRecordStorage({"name": "report.docx", "mime_type": None}),
    )

    resp = await upload.get_file_proxy("document/u1/abc.docx", _fake_request(), proxy=True)

    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == 'inline; filename="report.docx"'


@pytest.mark.asyncio
async def test_proxy_stream_without_record_serves_octet_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """查不到文件记录时依旧可代理，缺省 docx 的 MIME 推断不受影响。"""
    storage = _FakeS3Storage()
    monkeypatch.setattr(upload, "get_or_init_storage", _async_of(storage))
    monkeypatch.setattr(upload, "_file_record_storage", _FakeRecordStorage(None))

    resp = await upload.get_file_proxy("document/u1/abc.docx", _fake_request(), proxy=True)

    assert resp.status_code == 200
    assert "content-disposition" not in resp.headers
    assert (
        resp.media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
