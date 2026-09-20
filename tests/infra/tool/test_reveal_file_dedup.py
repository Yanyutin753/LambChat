"""reveal_file 产物去重契约：URL echo 归一 + 同内容跳过重传。

背景（产物全链路审查）：
- 模型按 ARTIFACT_POLICY 指示把 reveal 返回的代理 URL 复述进回复；该 URL
  再进 reveal_file 时，文件库若按 URL 建行会与原始 path 行裂成两行。
- 同一路径同内容的文件重复 reveal（auto 交付 + 显式 reveal、跨 turn 未改
  动重发）每次都全量重传新对象，旧行指向旧 key，存储孤儿无限累积。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.infra.storage.s3.types import UploadResult
from src.infra.tool import _reveal_file_support, reveal_file_tool


class _Runtime:
    def __init__(
        self,
        *,
        backend=object(),
        user_id: str | None = "user-1",
        session_id: str | None = "session-1",
        base_url: str = "https://app.example.com",
        trace_id: str | None = "trace-1",
    ) -> None:
        context = (
            SimpleNamespace(user_id=user_id, session_id=session_id) if user_id is not None else None
        )
        self.config = {
            "configurable": {
                "backend": backend,
                "base_url": base_url,
                "context": context,
                "trace_id": trace_id,
            }
        }


class _FakeUploadStorage:
    def __init__(self, exists: bool = True) -> None:
        self.uploads: list[str] = []
        self.exists = exists
        self.existence_checks: list[str] = []
        self._counter = 0

    async def file_exists(self, key: str) -> bool:
        self.existence_checks.append(key)
        return self.exists

    async def upload_file(self, *, file, folder, filename, content_type=None, **kwargs):
        self._counter += 1
        self.uploads.append(f"{folder}/{filename}")
        return UploadResult(
            key=f"{folder}/20260920_{self._counter:08d}_{filename}",
            url=f"https://oss.example.com/{folder}/{filename}",
            size=8,
            content_type=content_type or "application/octet-stream",
        )


class _FakeIndex:
    """文件库 fake：rows 按 dedupe 维度记忆，find_by_original/by_file_key 可查。"""

    def __init__(self) -> None:
        self.upserts: list[dict] = []
        self.rows: list[dict] = []

    async def upsert_by_name(self, **kwargs):
        self.upserts.append(kwargs)
        dedupe_key = kwargs.get("file_key")
        row = {
            "file_name": kwargs["file_name"],
            "file_key": kwargs["file_key"],
            "dedupe_key": dedupe_key,
            "content_hash": kwargs.get("data", {}).get("content_hash"),
            "original_path": kwargs.get("data", {}).get("original_path"),
            "file_size": kwargs.get("data", {}).get("file_size"),
        }
        self.rows = [r for r in self.rows if r["dedupe_key"] != dedupe_key] + [row]

    async def find_by_original(self, user_id, original_path, source):
        for row in reversed(self.rows):
            if row.get("original_path") == original_path:
                return row
        return None

    async def find_by_file_key(self, user_id, file_key, source=None):
        for row in reversed(self.rows):
            if row.get("file_key") == file_key:
                return row
        return None


class _FakeBackend:
    def __init__(self, content: bytes) -> None:
        self._content = content
        self.downloaded: list[str] = []

    async def adownload_files(self, paths):
        self.downloaded.extend(paths)
        return [SimpleNamespace(path=path, content=self._content, error=None) for path in paths]


@pytest.mark.asyncio
async def test_reveal_file_reverse_maps_self_upload_url_to_original_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本站代理 URL 进 reveal_file 时按 storage key 反查文件库，用原行的
    file_name/original_path 归一索引——URL echo 不再裂出第二行。"""
    storage = _FakeUploadStorage()
    index = _FakeIndex()
    index.rows = [
        {
            "file_name": "report.png",
            "file_key": "revealed_files/20260920_ab12cd34_report.png",
            "dedupe_key": "path:/workspace/report.png",
            "content_hash": None,
            "original_path": "/workspace/report.png",
            "file_size": 2048,
            "mime_type": "image/png",
            "url": "https://app.example.com/api/upload/file/revealed_files/20260920_ab12cd34_report.png",
        }
    ]
    echo_url = "https://app.example.com/api/upload/file/revealed_files/20260920_ab12cd34_report.png"

    async def _get_storage():
        return storage

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: index)
    monkeypatch.setattr(
        reveal_file_tool, "get_backend_from_runtime", lambda runtime: _FakeBackend(b"x")
    )

    await reveal_file_tool.reveal_file.coroutine(echo_url, runtime=_Runtime())

    assert len(index.upserts) == 1
    upsert = index.upserts[0]
    assert upsert["file_name"] == "report.png"
    assert upsert["file_key"] == "revealed_files/20260920_ab12cd34_report.png"
    assert upsert["data"]["original_path"] == "/workspace/report.png"
    # 并入原行时保留原行的真实元数据：不得用 echo 的 0 尺寸/URL 覆盖
    assert upsert["data"]["file_size"] == 2048
    assert (
        upsert["data"]["url"]
        == "https://app.example.com/api/upload/file/revealed_files/20260920_ab12cd34_report.png"
    )
    assert upsert["data"]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_reveal_file_reuses_upload_for_unchanged_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同路径同内容重复 reveal：第二次命中 content_hash 直接复用既有对象，
    不再重传（storage.upload_file 只允许被调用一次），URL 稳定。"""
    storage = _FakeUploadStorage()
    index = _FakeIndex()
    backend = _FakeBackend(b"identical-report-bytes")

    async def _get_storage():
        return storage

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: index)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: backend)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(_reveal_file_support, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool, "_get_reveal_file_upload_max_bytes", lambda: 10 * 1024 * 1024
    )
    monkeypatch.setattr(
        _reveal_file_support, "_get_reveal_file_upload_max_bytes", lambda: 10 * 1024 * 1024
    )

    first = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.png", runtime=_Runtime(backend=backend)
        )
    )
    second = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.png", runtime=_Runtime(backend=backend)
        )
    )

    assert first["success"] if "success" in first else "key" in first
    assert storage.uploads, "first reveal must upload"
    assert len(storage.uploads) == 1, "unchanged re-reveal must reuse the existing object"
    assert second["key"] == first["key"]
    assert second["url"] == first["url"]
    # 复用也要刷新索引（created_at 置顶逻辑依赖 upsert）
    assert len(index.upserts) == 2


@pytest.mark.asyncio
async def test_reveal_file_reuploads_when_content_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同路径内容变了 → 必须重传新对象（按轮展示新版本是预期行为）。"""
    storage = _FakeUploadStorage()
    index = _FakeIndex()

    async def _get_storage():
        return storage

    backend_holder = {"backend": _FakeBackend(b"v1-bytes")}

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: index)
    monkeypatch.setattr(
        reveal_file_tool,
        "get_backend_from_runtime",
        lambda runtime: backend_holder["backend"],
    )
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(_reveal_file_support, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool, "_get_reveal_file_upload_max_bytes", lambda: 10 * 1024 * 1024
    )
    monkeypatch.setattr(
        _reveal_file_support, "_get_reveal_file_upload_max_bytes", lambda: 10 * 1024 * 1024
    )

    first = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.png",
            runtime=_Runtime(backend=backend_holder["backend"]),
        )
    )
    backend_holder["backend"] = _FakeBackend(b"v2-bytes-modified")
    second = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.png",
            runtime=_Runtime(backend=backend_holder["backend"]),
        )
    )

    assert len(storage.uploads) == 2
    assert second["key"] != first["key"]


@pytest.mark.asyncio
async def test_reveal_file_reuploads_when_reused_object_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """复用自愈：文件库行命中但存储对象已被删除 → 必须重传新对象并让
    upsert 修复行；否则哈希永远命中死 key，产物永久 404。"""
    storage = _FakeUploadStorage(exists=False)
    index = _FakeIndex()

    async def _get_storage():
        return storage

    backend = _FakeBackend(b"stable-bytes")

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: index)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: backend)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(_reveal_file_support, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool, "_get_reveal_file_upload_max_bytes", lambda: 10 * 1024 * 1024
    )
    monkeypatch.setattr(
        _reveal_file_support, "_get_reveal_file_upload_max_bytes", lambda: 10 * 1024 * 1024
    )

    first = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.png", runtime=_Runtime(backend=backend)
        )
    )
    # 第一次上传后，存储侧对象被清（file_exists=False）但库行仍在
    second = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.png", runtime=_Runtime(backend=backend)
        )
    )

    assert len(storage.uploads) == 2, "stale row must not pin a dead object"
    assert second["key"] != first["key"]
    assert len(index.upserts) == 2


@pytest.mark.asyncio
async def test_reveal_file_legacy_row_without_hash_falls_back_to_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧数据兼容：本特性之前的库行没有 content_hash → 不命中复用、正常
    上传，且 upsert 补写哈希（后续 reveal 开始享受复用）。"""
    storage = _FakeUploadStorage()
    index = _FakeIndex()
    index.rows = [
        {
            "file_name": "report.png",
            "file_key": "revealed_files/20260101_deadbeef_report.png",
            "dedupe_key": "path:/workspace/report.png",
            "content_hash": None,
            "original_path": "/workspace/report.png",
            "file_size": 2048,
        }
    ]
    backend = _FakeBackend(b"fresh-bytes")

    async def _get_storage():
        return storage

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(_reveal_file_support, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: index)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: backend)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(_reveal_file_support, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool, "_get_reveal_file_upload_max_bytes", lambda: 10 * 1024 * 1024
    )
    monkeypatch.setattr(
        _reveal_file_support, "_get_reveal_file_upload_max_bytes", lambda: 10 * 1024 * 1024
    )

    first = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.png", runtime=_Runtime(backend=backend)
        )
    )

    assert len(storage.uploads) == 1, "legacy row without hash must not be reused"
    assert first["key"] != "revealed_files/20260101_deadbeef_report.png"
    assert index.upserts[-1]["data"]["content_hash"]  # 补写哈希，后续可复用
