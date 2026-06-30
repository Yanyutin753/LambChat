from __future__ import annotations

import gc
import json
import weakref
from types import SimpleNamespace

import pytest

from src.infra.tool import reveal_file_tool


class _Runtime:
    def __init__(
        self,
        *,
        backend=object(),
        user_id: str | None = "user-1",
        session_id: str | None = "session-1",
        base_url: str = "https://app.example.com",
        trace_id: str | None = None,
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


class _TrackableBytes(bytearray):
    pass


class _BlockingOnlySpooledFile:
    def __init__(self, *args, **kwargs) -> None:
        self.data = bytearray()
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def write(self, chunk: bytes) -> int:
        if not getattr(reveal_file_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("reveal_file spool writes must run in blocking IO executor")
        self.data.extend(chunk)
        self.position += len(chunk)
        return len(chunk)

    def seek(self, position: int) -> int:
        if not getattr(reveal_file_tool, "_inside_fake_blocking_io", False):
            raise AssertionError("reveal_file spool seek must run in blocking IO executor")
        self.position = position
        return position

    def read(self) -> bytes:
        return bytes(self.data)


def test_reveal_file_runtime_is_injected_not_model_argument() -> None:
    assert "runtime" not in reveal_file_tool.reveal_file.args


@pytest.mark.asyncio
async def test_reveal_file_returns_remote_url_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocking_calls: list[object] = []

    async def _get_storage():
        raise AssertionError("remote URL reveal should not initialize storage")

    def _get_backend_from_runtime(runtime):
        raise AssertionError("remote URL reveal should not inspect backend")

    async def fake_run_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func)
        return func(*args, **kwargs)

    url = (
        "https://cdn.example.com/generated-images%2Fuser-1%2Fportrait.png"
        "?response-content-disposition=inline&Expires=1780067399"
    )

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", _get_backend_from_runtime)
    monkeypatch.setattr(reveal_file_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            url,
            description="AI generated portrait",
            runtime=object(),
        )
    )

    assert result == {
        "key": url,
        "url": url,
        "name": "portrait.png",
        "type": "image",
        "mime_type": "image/png",
        "size": 0,
        "_meta": {
            "path": url,
            "description": "AI generated portrait",
            "source": "remote_url",
        },
    }
    assert json.dumps in blocking_calls


@pytest.mark.asyncio
async def test_reveal_file_indexes_remote_url_without_storage_or_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    indexed_calls: list[dict[str, object]] = []

    async def _get_storage():
        raise AssertionError("remote URL reveal should not initialize upload storage")

    def _get_backend_from_runtime(runtime):
        raise AssertionError("remote URL reveal should not inspect backend")

    class _FakeIndex:
        async def upsert_by_name(self, **kwargs):
            indexed_calls.append(kwargs)

    url = "https://cdn.example.com/generated-images/user-1/portrait.png"

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", _get_backend_from_runtime)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: _FakeIndex())

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            url,
            description="AI generated portrait",
            runtime=_Runtime(trace_id="trace-remote"),
        )
    )

    assert result["url"] == url
    assert indexed_calls == [
        {
            "user_id": "user-1",
            "file_name": "portrait.png",
            "source": "reveal_file",
            "file_key": url,
            "trace_id": "trace-remote",
            "data": {
                "file_type": "image",
                "mime_type": "image/png",
                "file_size": 0,
                "url": url,
                "session_id": "session-1",
                "project_id": None,
                "description": "AI generated portrait",
                "original_path": url,
            },
        }
    ]


@pytest.mark.asyncio
async def test_reveal_file_backend_unavailable_offloads_result_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocking_calls: list[object] = []

    async def _get_storage():
        return object()

    async def fake_run_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: None)
    monkeypatch.setattr(reveal_file_tool, "run_blocking_io", fake_run_blocking_io)

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.pdf",
            description="missing backend",
            runtime=object(),
        )
    )

    assert result["type"] == "file_reveal"
    assert result["file"]["path"] == "/workspace/report.pdf"
    assert json.dumps in blocking_calls


@pytest.mark.asyncio
async def test_upload_local_resource_skips_filesystem_fallback_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _download_file_from_backend(backend, file_path: str):
        return None

    async def _read_file_from_filesystem(file_path: str):
        raise AssertionError("filesystem fallback should be disabled")

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_read_file_from_filesystem", _read_file_from_filesystem)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(ENABLE_LOCAL_FILESYSTEM_FALLBACK=False),
    )

    result = await reveal_file_tool._upload_local_resource(
        "./chart.png",
        "/workspace",
        backend=object(),
        storage=object(),
        base_url="http://example.com",
    )

    assert result is None


@pytest.mark.asyncio
async def test_upload_local_resource_uses_filesystem_fallback_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    uploaded: list[tuple[bytes, str, str]] = []
    chart_path = tmp_path / "workspace" / "chart.png"
    chart_path.parent.mkdir()
    chart_path.write_bytes(b"png-bytes")

    async def _download_file_from_backend(backend, file_path: str):
        return None

    async def _read_file_from_filesystem(file_path: str):
        raise AssertionError("local filesystem fallback should stream from disk")

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
            del skip_size_limit
            uploaded.append((file.read(), folder, filename))
            return SimpleNamespace(key=f"{folder}/{filename}")

        async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
            raise AssertionError("local filesystem fallback should not materialize bytes")

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_read_file_from_filesystem", _read_file_from_filesystem)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(ENABLE_LOCAL_FILESYSTEM_FALLBACK=True),
    )

    result = await reveal_file_tool._upload_local_resource(
        "./chart.png",
        str(chart_path.parent),
        backend=object(),
        storage=_FakeStorage(),
        base_url="http://example.com",
    )

    assert result == "http://example.com/api/upload/file/revealed_files/chart.png"
    assert uploaded == [(b"png-bytes", "revealed_files", "chart.png")]


@pytest.mark.asyncio
async def test_upload_local_resource_uses_filesystem_upload_helper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    chart_path = tmp_path / "workspace" / "chart.png"
    chart_path.parent.mkdir()
    chart_path.write_bytes(b"png-bytes")
    helper_calls: list[tuple[str, str, str]] = []

    async def _download_file_from_backend(backend, file_path: str):
        return None

    async def _upload_filesystem_file(file_path, storage, filename, mime_type):
        del storage
        helper_calls.append((file_path, filename, mime_type))
        return SimpleNamespace(key=f"revealed_files/{filename}")

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_upload_filesystem_file", _upload_filesystem_file)
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(ENABLE_LOCAL_FILESYSTEM_FALLBACK=True),
    )

    result = await reveal_file_tool._upload_local_resource(
        "./chart.png",
        str(chart_path.parent),
        backend=object(),
        storage=object(),
        base_url="http://example.com",
    )

    assert result == "http://example.com/api/upload/file/revealed_files/chart.png"
    assert helper_calls == [(str(chart_path), "chart.png", "image/png")]


@pytest.mark.asyncio
async def test_reveal_file_uploads_backend_content_as_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded: dict[str, object] = {}
    blocking_calls: list[str] = []

    async def _download_file_from_backend(backend, file_path: str):
        assert file_path == "/workspace/report.pdf"
        return b"pdf-bytes"

    class _FakeStorage:
        async def upload_bytes(self, **_kwargs):
            raise AssertionError("reveal_file should upload backend content with upload_file")

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
                url=f"https://storage.example.com/{folder}/{filename}",
                content_type=content_type,
                size=len(uploaded["data"]),
            )

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )

    async def fake_run_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func.__name__)
        monkeypatch.setattr(reveal_file_tool, "_inside_fake_blocking_io", True, raising=False)
        try:
            return func(*args, **kwargs)
        finally:
            monkeypatch.setattr(reveal_file_tool, "_inside_fake_blocking_io", False, raising=False)

    monkeypatch.setattr(reveal_file_tool, "SpooledTemporaryFile", _BlockingOnlySpooledFile)
    monkeypatch.setattr(reveal_file_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(reveal_file_tool, "_inside_fake_blocking_io", False, raising=False)

    async def _get_storage():
        return _FakeStorage()

    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: object())
    monkeypatch.setattr(
        reveal_file_tool,
        "get_base_url_from_runtime",
        lambda runtime: "https://app.example.com",
    )

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.pdf",
            description="monthly report",
            runtime=object(),
        )
    )

    assert result["url"] == "https://app.example.com/api/upload/file/revealed_files/report.pdf"
    assert uploaded == {
        "data": b"pdf-bytes",
        "folder": "revealed_files",
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "skip_size_limit": True,
    }
    assert blocking_calls == ["write", "seek", "dumps"]


@pytest.mark.asyncio
async def test_reveal_file_rejects_known_oversize_backend_file_before_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = "/workspace/huge.pdf"
    max_bytes = 8

    class _FakeBackend:
        def __init__(self) -> None:
            self.download_called = False

        async def aget_file_size(self, path: str) -> int:
            assert path == source_path
            return max_bytes + 1

    backend = _FakeBackend()

    async def _download_file_from_backend(_backend, _file_path: str):
        backend.download_called = True
        raise AssertionError("oversized backend file should not be downloaded")

    class _FakeStorage:
        async def upload_file(self, **_kwargs):
            raise AssertionError("oversized backend file should not be uploaded")

    async def _get_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(S3_INTERNAL_UPLOAD_MAX_SIZE=max_bytes),
    )
    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: backend)

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            source_path,
            description="too big",
            runtime=object(),
        )
    )

    assert result["type"] == "file_reveal"
    assert result["file"]["path"] == source_path
    assert result["file"]["error"] == "file_too_large"
    assert result["file"]["size"] == max_bytes + 1
    assert backend.download_called is False


@pytest.mark.asyncio
async def test_reveal_file_rejects_unknown_oversize_backend_file_after_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = "/workspace/huge.pdf"
    max_bytes = 8

    class _FakeStorage:
        async def upload_file(self, **_kwargs):
            raise AssertionError("oversized backend file should not be uploaded")

    async def _get_storage():
        return _FakeStorage()

    async def _download_file_from_backend(_backend, _file_path: str):
        return b"x" * (max_bytes + 1)

    class _FailSpooledFile:
        def __init__(self, *args, **kwargs):
            raise AssertionError("oversized backend file should not be copied into spool")

    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(S3_INTERNAL_UPLOAD_MAX_SIZE=max_bytes),
    )
    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "SpooledTemporaryFile", _FailSpooledFile)
    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: object())

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            source_path,
            description="too big",
            runtime=object(),
        )
    )

    assert result["type"] == "file_reveal"
    assert result["file"]["path"] == source_path
    assert result["file"]["error"] == "file_too_large"
    assert result["file"]["size"] == max_bytes + 1


@pytest.mark.asyncio
async def test_reveal_file_releases_backend_buffer_before_upload_await(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released_before_upload_completed = False
    buffer_ref: weakref.ReferenceType[_TrackableBytes] | None = None

    async def _download_file_from_backend(backend, file_path: str):
        del backend, file_path
        nonlocal buffer_ref
        data = _TrackableBytes(b"x" * 32)
        buffer_ref = weakref.ref(data)
        return data

    class _FakeStorage:
        async def upload_bytes(self, **_kwargs):
            raise AssertionError("reveal_file should upload backend content with upload_file")

        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str,
            *,
            skip_size_limit: bool = False,
        ):
            del file, folder, filename, content_type, skip_size_limit
            nonlocal released_before_upload_completed
            gc.collect()
            released_before_upload_completed = buffer_ref() is None
            return SimpleNamespace(
                key="revealed_files/report.pdf",
                url="https://storage.example.com/revealed_files/report.pdf",
                content_type="application/pdf",
                size=32,
            )

    async def _get_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: object())
    monkeypatch.setattr(
        reveal_file_tool,
        "get_base_url_from_runtime",
        lambda runtime: "https://app.example.com",
    )

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.pdf",
            description="monthly report",
            runtime=object(),
        )
    )

    assert result["url"] == "https://app.example.com/api/upload/file/revealed_files/report.pdf"
    assert released_before_upload_completed is True


@pytest.mark.asyncio
async def test_reveal_file_indexes_upload_when_runtime_has_user_without_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    indexed_calls: list[dict[str, object]] = []

    async def _download_file_from_backend(backend, file_path: str):
        assert file_path == "/workspace/report.pdf"
        return b"pdf-bytes"

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
            del file, skip_size_limit
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                url=f"https://storage.example.com/{folder}/{filename}",
                content_type=content_type,
                size=9,
            )

    class _FakeIndex:
        async def upsert_by_name(self, **kwargs):
            indexed_calls.append(kwargs)

    async def _get_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_revealed_file_storage", lambda: _FakeIndex())

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            "/workspace/report.pdf",
            description="monthly report",
            runtime=_Runtime(trace_id="trace-runtime"),
        )
    )

    assert result["url"] == "https://app.example.com/api/upload/file/revealed_files/report.pdf"
    assert indexed_calls == [
        {
            "user_id": "user-1",
            "file_name": "report.pdf",
            "source": "reveal_file",
            "file_key": "revealed_files/report.pdf",
            "trace_id": "trace-runtime",
            "data": {
                "file_type": "document",
                "mime_type": "application/pdf",
                "file_size": 9,
                "url": result["url"],
                "session_id": "session-1",
                "project_id": None,
                "description": "monthly report",
                "original_path": "/workspace/report.pdf",
            },
        }
    ]


@pytest.mark.asyncio
async def test_reveal_file_filesystem_fallback_streams_main_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    uploaded: dict[str, object] = {}
    report_path = tmp_path / "report.pdf"
    report_path.write_bytes(b"pdf-bytes")
    blocking_calls: list[str] = []

    async def _download_file_from_backend(backend, file_path: str):
        return None

    async def _read_file_from_filesystem(file_path: str):
        raise AssertionError("main filesystem fallback should stream from disk")

    class _FakeStorage:
        async def upload_bytes(self, **_kwargs):
            raise AssertionError("main filesystem fallback should not materialize bytes")

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
                url=f"https://storage.example.com/{folder}/{filename}",
                content_type=content_type,
                size=len(uploaded["data"]),
            )

    async def _get_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_read_file_from_filesystem", _read_file_from_filesystem)
    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: object())
    monkeypatch.setattr(
        reveal_file_tool,
        "get_base_url_from_runtime",
        lambda runtime: "https://app.example.com",
    )
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)

    async def fake_run_blocking_io(func, *args, **kwargs):
        blocking_calls.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(reveal_file_tool, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(ENABLE_LOCAL_FILESYSTEM_FALLBACK=True),
    )

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            str(report_path),
            description="local report",
            runtime=object(),
        )
    )

    assert result["url"] == "https://app.example.com/api/upload/file/revealed_files/report.pdf"
    assert uploaded == {
        "data": b"pdf-bytes",
        "folder": "revealed_files",
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "skip_size_limit": True,
    }
    assert "_is_file_path" in blocking_calls


@pytest.mark.asyncio
async def test_reveal_file_large_resolvable_filesystem_fallback_skips_ref_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    uploaded: dict[str, object] = {}
    report_path = tmp_path / "report.md"
    report_path.write_bytes(b"x" * 64)

    async def _download_file_from_backend(backend, file_path: str):
        return None

    async def _read_file_from_filesystem(file_path: str):
        raise AssertionError("large local markdown should stay on streaming upload path")

    class _FakeStorage:
        async def upload_bytes(self, **_kwargs):
            raise AssertionError("main filesystem fallback should not materialize bytes")

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
                url=f"https://storage.example.com/{folder}/{filename}",
                content_type=content_type,
                size=len(uploaded["data"]),
            )

    async def _get_storage():
        return _FakeStorage()

    monkeypatch.setattr(
        reveal_file_tool, "_download_file_from_backend", _download_file_from_backend
    )
    monkeypatch.setattr(reveal_file_tool, "_read_file_from_filesystem", _read_file_from_filesystem)
    monkeypatch.setattr(reveal_file_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_file_tool, "get_backend_from_runtime", lambda runtime: object())
    monkeypatch.setattr(
        reveal_file_tool,
        "get_base_url_from_runtime",
        lambda runtime: "https://app.example.com",
    )
    monkeypatch.setattr(reveal_file_tool, "_is_sandbox_backend", lambda backend: False)
    monkeypatch.setattr(reveal_file_tool, "_LOCAL_REF_RESOLUTION_MAX_BYTES", 8)
    monkeypatch.setattr(
        reveal_file_tool,
        "settings",
        SimpleNamespace(ENABLE_LOCAL_FILESYSTEM_FALLBACK=True),
    )

    result = json.loads(
        await reveal_file_tool.reveal_file.coroutine(
            str(report_path),
            description="large local markdown",
            runtime=object(),
        )
    )

    assert result["url"] == "https://app.example.com/api/upload/file/revealed_files/report.md"
    assert uploaded == {
        "data": b"x" * 64,
        "folder": "revealed_files",
        "filename": "report.md",
        "content_type": "text/markdown",
        "skip_size_limit": True,
    }


@pytest.mark.asyncio
async def test_read_file_from_filesystem_refuses_large_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    report_path = tmp_path / "large.md"
    report_path.write_bytes(b"x" * 16)
    monkeypatch.setattr(reveal_file_tool, "_LOCAL_REF_RESOLUTION_MAX_BYTES", 8)

    content = await reveal_file_tool._read_file_from_filesystem(str(report_path))

    assert content is None


@pytest.mark.asyncio
async def test_resolve_local_references_caps_uploaded_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded_refs: list[str] = []
    markdown = "\n".join(f"![chart {index}](./chart-{index}.png)" for index in range(5))

    async def _upload_local_resource(
        local_path: str,
        file_dir,
        backend,
        storage,
        base_url,
    ) -> str:
        del file_dir, backend, storage, base_url
        uploaded_refs.append(local_path)
        return f"https://app.example.com/{local_path.lstrip('./')}"

    monkeypatch.setattr(reveal_file_tool, "_LOCAL_REF_UPLOAD_LIMIT", 2, raising=False)
    monkeypatch.setattr(reveal_file_tool, "_upload_local_resource", _upload_local_resource)

    resolved = await reveal_file_tool._resolve_local_references(
        markdown.encode(),
        "/workspace",
        backend=object(),
        storage=object(),
        base_url="https://app.example.com",
    )

    text = resolved.decode()
    assert uploaded_refs == ["./chart-0.png", "./chart-1.png"]
    assert "https://app.example.com/chart-0.png" in text
    assert "https://app.example.com/chart-1.png" in text
    assert "./chart-2.png" in text
