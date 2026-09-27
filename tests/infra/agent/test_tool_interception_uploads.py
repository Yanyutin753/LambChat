from __future__ import annotations

import base64
import gc
import json
import weakref
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import ToolMessage

from src.infra.agent.middleware import tool_interception


class _TrackableBytes(bytearray):
    pass


@pytest.mark.asyncio
async def test_binary_block_upload_uses_file_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    uploaded: list[tuple[bytes, str, str, str | None]] = []

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            del skip_size_limit
            uploaded.append((file.read(), folder, filename, content_type))
            return SimpleNamespace(key=f"{folder}/{filename}")

        async def upload_bytes(self, *args: Any, **kwargs: Any):
            raise AssertionError("binary block upload should not use upload_bytes")

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        tool_interception.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abc1234567890"),
    )

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    url = await middleware._upload_block(
        {
            "base64": base64.b64encode(b"binary-data").decode("ascii"),
            "mime_type": "image/png",
        }
    )

    assert url == "https://app.example.com/api/upload/file/tool_binaries/binary_abc12345.png"
    assert uploaded == [(b"binary-data", "tool_binaries", "binary_abc12345.png", "image/png")]


@pytest.mark.asyncio
async def test_binary_block_upload_offloads_decode_and_spool_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded: list[tuple[bytes, str, str, str | None]] = []
    inside_blocking_io = False

    class _GuardedSpooledFile:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            self._buffer = BytesIO()

        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            self._buffer.close()

        def write(self, data: bytes) -> int:
            assert inside_blocking_io, "spool writes must be offloaded from the event loop"
            return self._buffer.write(data)

        def seek(self, offset: int, whence: int = 0) -> int:
            assert inside_blocking_io, "spool seeks must be offloaded from the event loop"
            return self._buffer.seek(offset, whence)

        def read(self, size: int = -1) -> bytes:
            return self._buffer.read(size)

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            del skip_size_limit
            uploaded.append((file.read(), folder, filename, content_type))
            return SimpleNamespace(key=f"{folder}/{filename}")

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        kwargs.pop("urgent", None)
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(tool_interception, "SpooledTemporaryFile", _GuardedSpooledFile)
    monkeypatch.setattr(tool_interception, "run_long_blocking_io", _fake_run_blocking_io)
    monkeypatch.setattr(
        tool_interception.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abc1234567890"),
    )

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    url = await middleware._upload_block(
        {
            "base64": base64.b64encode(b"binary-data").decode("ascii"),
            "mime_type": "image/png",
        }
    )

    assert url == "https://app.example.com/api/upload/file/tool_binaries/binary_abc12345.png"
    assert uploaded == [(b"binary-data", "tool_binaries", "binary_abc12345.png", "image/png")]


@pytest.mark.asyncio
async def test_binary_block_upload_rejects_oversized_payload_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_init_calls = 0

    class _FakeStorage:
        async def upload_file(self, *args: Any, **kwargs: Any):
            raise AssertionError("oversized binary block should not be uploaded")

    async def _fake_get_storage() -> _FakeStorage:
        nonlocal storage_init_calls
        storage_init_calls += 1
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(tool_interception, "_BINARY_BLOCK_UPLOAD_MAX_BYTES", 4, raising=False)

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    url = await middleware._upload_block(
        {
            "base64": base64.b64encode(b"binary-data").decode("ascii"),
            "mime_type": "image/png",
        }
    )

    assert url is None
    assert storage_init_calls == 0


@pytest.mark.asyncio
async def test_read_file_binary_upload_uses_file_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    uploaded: list[tuple[bytes, str, str, str | None]] = []

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            assert paths == ["/workspace/chart.png"]
            return [SimpleNamespace(content=b"png-data")]

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            del skip_size_limit
            uploaded.append((file.read(), folder, filename, content_type))
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                content_type=content_type,
            )

        async def upload_bytes(self, *args: Any, **kwargs: Any):
            raise AssertionError("read_file binary upload should not use upload_bytes")

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(runtime=object(), tool_call={"id": "call-1"})

    message = await middleware._handle_read_file_binary(request, "/workspace/chart.png")

    assert message is not None
    payload = json.loads(message.content)
    assert payload["key"] == "revealed_files/chart.png"
    assert payload["url"] == "https://app.example.com/api/upload/file/revealed_files/chart.png"
    assert payload["size"] == len(b"png-data")
    assert uploaded == [(b"png-data", "revealed_files", "chart.png", "image/png")]


@pytest.mark.asyncio
async def test_read_file_binary_upload_offloads_spool_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded: list[tuple[bytes, str, str, str | None]] = []
    inside_blocking_io = False

    class _GuardedSpooledFile:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs
            self._buffer = BytesIO()

        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            self._buffer.close()

        def write(self, data: bytes) -> int:
            assert inside_blocking_io, "spool writes must be offloaded from the event loop"
            return self._buffer.write(data)

        def seek(self, offset: int, whence: int = 0) -> int:
            assert inside_blocking_io, "spool seeks must be offloaded from the event loop"
            return self._buffer.seek(offset, whence)

        def read(self, size: int = -1) -> bytes:
            return self._buffer.read(size)

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            assert paths == ["/workspace/chart.png"]
            return [SimpleNamespace(content=b"png-data")]

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            del skip_size_limit
            uploaded.append((file.read(), folder, filename, content_type))
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                content_type=content_type,
            )

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        kwargs.pop("urgent", None)
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )
    monkeypatch.setattr(tool_interception, "SpooledTemporaryFile", _GuardedSpooledFile)
    monkeypatch.setattr(tool_interception, "run_long_blocking_io", _fake_run_blocking_io)

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(runtime=object(), tool_call={"id": "call-1"})

    message = await middleware._handle_read_file_binary(request, "/workspace/chart.png")

    assert message is not None
    assert uploaded == [(b"png-data", "revealed_files", "chart.png", "image/png")]


@pytest.mark.asyncio
async def test_read_file_binary_upload_offloads_result_json_formatting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            assert paths == ["/workspace/chart.png"]
            return [SimpleNamespace(content=b"png-data")]

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            del file, skip_size_limit
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                content_type=content_type,
            )

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        kwargs.pop("urgent", None)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )
    monkeypatch.setattr(tool_interception, "run_long_blocking_io", _fake_run_blocking_io)

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(runtime=object(), tool_call={"id": "call-1"})

    message = await middleware._handle_read_file_binary(request, "/workspace/chart.png")

    assert message is not None
    assert calls == [tool_interception._write_bytes_to_file, json.dumps]
    assert json.loads(message.content)["url"] == (
        "https://app.example.com/api/upload/file/revealed_files/chart.png"
    )


@pytest.mark.asyncio
async def test_read_file_binary_upload_releases_download_buffer_before_upload_await(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released_before_upload_completed = False
    buffer_ref: weakref.ReferenceType[_TrackableBytes] | None = None

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            assert paths == ["/workspace/chart.png"]
            nonlocal buffer_ref
            data = _TrackableBytes(b"png-data")
            buffer_ref = weakref.ref(data)
            return [SimpleNamespace(content=data)]

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            del file, folder, filename, content_type, skip_size_limit
            nonlocal released_before_upload_completed
            gc.collect()
            released_before_upload_completed = buffer_ref() is None
            return SimpleNamespace(
                key="revealed_files/chart.png",
                content_type="image/png",
            )

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(runtime=object(), tool_call={"id": "call-1"})

    message = await middleware._handle_read_file_binary(request, "/workspace/chart.png")

    assert message is not None
    assert released_before_upload_completed is True


@pytest.mark.asyncio
async def test_read_file_binary_upload_refuses_oversized_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            assert paths == ["/workspace/huge.png"]
            return [SimpleNamespace(content=b"x" * 16)]

    storage_init_calls = 0

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            return SimpleNamespace(
                key=f"{folder}/{filename}",
                content_type=content_type,
            )

    async def _fake_get_storage():
        nonlocal storage_init_calls
        storage_init_calls += 1
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )
    monkeypatch.setattr(tool_interception, "_READ_FILE_BINARY_UPLOAD_MAX_BYTES", 8, raising=False)

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(runtime=object(), tool_call={"id": "call-1"})

    message = await middleware._handle_read_file_binary(request, "/workspace/huge.png")

    assert message is None
    assert storage_init_calls == 0


@pytest.mark.asyncio
async def test_read_file_binary_upload_checks_backend_size_before_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_called = False

    class _FakeBackend:
        async def aget_file_size(self, path: str):
            assert path == "/workspace/huge.png"
            return 16

        async def adownload_files(self, paths: list[str]):
            nonlocal download_called
            assert paths == ["/workspace/huge.png"]
            download_called = True
            return [SimpleNamespace(content=b"small-after-download")]

    storage_init_calls = 0

    class _FakeStorage:
        async def upload_file(self, *args: Any, **kwargs: Any):
            return SimpleNamespace(
                key="revealed_files/huge.png",
                content_type="image/png",
            )

    async def _fake_get_storage():
        nonlocal storage_init_calls
        storage_init_calls += 1
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )
    monkeypatch.setattr(tool_interception, "_READ_FILE_BINARY_UPLOAD_MAX_BYTES", 8, raising=False)

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(runtime=object(), tool_call={"id": "call-1"})

    message = await middleware._handle_read_file_binary(request, "/workspace/huge.png")

    assert message is None
    assert download_called is False
    assert storage_init_calls == 0


@pytest.mark.asyncio
async def test_read_file_binary_interception_emits_tool_lifecycle_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """二进制 read_file 拦截路径必须补发 tool:start / tool:result。

    拦截直接构造 ToolMessage 返回（不经真实工具执行），LangGraph 的
    on_tool_start/on_tool_end 不会触发；不补发的话前端只收到流式参数，
    「读取文件」卡片永远等不到结果（生产 8b08290d 会话实测）。
    """
    emitted: list[dict[str, Any]] = []

    class _FakePresenter:
        def present_tool_start(
            self, tool_name, tool_input, tool_call_id=None, depth=0, agent_id=None
        ):
            return {
                "event": "tool:start",
                "data": {
                    "tool": tool_name,
                    "args": tool_input,
                    "tool_call_id": tool_call_id,
                    "depth": depth,
                },
            }

        def present_tool_result(
            self,
            tool_name,
            result,
            tool_call_id=None,
            success=True,
            error=None,
            depth=0,
            agent_id=None,
        ):
            return {
                "event": "tool:result",
                "data": {
                    "tool": tool_name,
                    "result": result,
                    "success": success,
                    "tool_call_id": tool_call_id,
                    "depth": depth,
                },
            }

        async def emit(self, event):
            emitted.append(event)

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            assert paths == ["/workspace/chart.png"]
            return [SimpleNamespace(content=b"png-data")]

    class _FakeStorage:
        async def upload_file(
            self,
            file,
            folder: str,
            filename: str,
            content_type: str | None = None,
            *,
            skip_size_limit: bool = False,
        ):
            del file, skip_size_limit
            return SimpleNamespace(key=f"{folder}/{filename}", content_type=content_type)

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            config={
                "configurable": {
                    "presenter": _FakePresenter(),
                    "checkpoint_ns": "tools:task-1",
                }
            }
        ),
        tool_call={
            "name": "read_file",
            "id": "call-1",
            "args": {"file_path": "/workspace/chart.png"},
        },
    )

    async def _handler(_request: Any) -> Any:
        raise AssertionError("binary read_file must be intercepted before the real handler")

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, ToolMessage)
    assert [event["event"] for event in emitted] == ["tool:start", "tool:result"]
    start_event, result_event = emitted
    assert start_event["data"]["tool"] == "read_file"
    assert start_event["data"]["args"] == {"file_path": "/workspace/chart.png"}
    assert start_event["data"]["tool_call_id"].startswith("tools:task-1|")
    assert result_event["data"]["tool"] == "read_file"
    assert result_event["data"]["success"] is True
    assert result_event["data"]["result"]["url"] == (
        "https://app.example.com/api/upload/file/revealed_files/chart.png"
    )
    assert result_event["data"]["tool_call_id"] == start_event["data"]["tool_call_id"]


@pytest.mark.asyncio
async def test_read_file_binary_interception_survives_presenter_emit_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """事件发射异常不得影响工具链路：ToolMessage 照常返回。"""

    class _ExplodingPresenter:
        def present_tool_start(self, *args: Any, **kwargs: Any):
            return {"event": "tool:start", "data": {}}

        def present_tool_result(self, *args: Any, **kwargs: Any):
            return {"event": "tool:result", "data": {}}

        async def emit(self, event):
            raise RuntimeError("presenter unavailable")

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(content=b"png-data")]

    class _FakeStorage:
        async def upload_file(
            self, file, folder, filename, content_type=None, *, skip_size_limit=False
        ):
            del file, skip_size_limit
            return SimpleNamespace(key=f"{folder}/{filename}", content_type=content_type)

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(
        runtime=SimpleNamespace(
            config={
                "configurable": {
                    "presenter": _ExplodingPresenter(),
                    "checkpoint_ns": "tools:task-1",
                }
            }
        ),
        tool_call={
            "name": "read_file",
            "id": "call-1",
            "args": {"file_path": "/workspace/chart.png"},
        },
    )

    async def _handler(_request: Any) -> Any:
        raise AssertionError("binary read_file must be intercepted before the real handler")

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, ToolMessage)
    assert json.loads(result.content)["url"] == (
        "https://app.example.com/api/upload/file/revealed_files/chart.png"
    )


@pytest.mark.asyncio
async def test_read_file_binary_interception_without_presenter_returns_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 presenter（非图上下文/旧调用方）时不发事件，拦截结果照常返回。"""

    class _FakeBackend:
        async def adownload_files(self, paths: list[str]):
            return [SimpleNamespace(content=b"png-data")]

    class _FakeStorage:
        async def upload_file(
            self, file, folder, filename, content_type=None, *, skip_size_limit=False
        ):
            del file, skip_size_limit
            return SimpleNamespace(key=f"{folder}/{filename}", content_type=content_type)

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )
    monkeypatch.setattr(
        "src.infra.tool.backend_utils.get_backend_from_runtime",
        lambda runtime: _FakeBackend(),
    )

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    request = SimpleNamespace(
        runtime=SimpleNamespace(config={"configurable": {}}),
        tool_call={
            "name": "read_file",
            "id": "call-1",
            "args": {"file_path": "/workspace/chart.png"},
        },
    )

    async def _handler(_request: Any) -> Any:
        raise AssertionError("binary read_file must be intercepted before the real handler")

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, ToolMessage)
    assert json.loads(result.content)["url"] == (
        "https://app.example.com/api/upload/file/revealed_files/chart.png"
    )


@pytest.mark.asyncio
async def test_binary_middleware_offloads_uploaded_block_json_formatting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        kwargs.pop("urgent", None)
        return func(*args, **kwargs)

    monkeypatch.setattr(tool_interception, "run_long_blocking_io", _fake_run_blocking_io)

    middleware = tool_interception.ToolResultBinaryMiddleware(base_url="https://app.example.com")
    payload = await middleware._format_uploaded_blocks_for_llm(
        [
            {"type": "text", "text": "generated chart"},
            {"type": "image", "mime_type": "image/png", "url": "https://app.example.com/i.png"},
        ]
    )

    assert calls == [json.dumps]
    assert json.loads(payload) == {
        "text": "generated chart",
        "blocks": [
            {
                "type": "image",
                "mime_type": "image/png",
                "url": "https://app.example.com/i.png",
            }
        ],
    }


@pytest.mark.asyncio
async def test_tool_search_middleware_offloads_deferred_tool_dict_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    async def _fake_run_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        kwargs.pop("urgent", None)
        return func(*args, **kwargs)

    class _DeferredTool:
        async def ainvoke(self, args: dict[str, Any]) -> dict[str, Any]:
            assert args == {"query": "large"}
            return {"items": ["x" * 20_000]}

    class _DeferredManager:
        def is_discovered(self, tool_name: str) -> bool:
            return tool_name == "deferred_tool"

        def get_tool(self, tool_name: str) -> _DeferredTool:
            assert tool_name == "deferred_tool"
            return _DeferredTool()

        def get_deferred_stubs_string(self) -> str:
            return ""

        def get_discovered_tools(self) -> list[Any]:
            return []

    monkeypatch.setattr(tool_interception, "run_long_blocking_io", _fake_run_blocking_io)

    middleware = tool_interception.ToolSearchMiddleware(
        deferred_manager=_DeferredManager(),
    )
    middleware._search_tool = SimpleNamespace(name="search_tools")
    request = SimpleNamespace(
        tool_call={"name": "deferred_tool", "id": "call-1", "args": {"query": "large"}},
        tool=None,
    )

    async def _handler(_request: Any) -> Any:
        raise AssertionError("discovered deferred tool should execute directly")

    message = await middleware.awrap_tool_call(request, _handler)

    assert calls == [json.dumps]
    assert message.content.startswith('{"items":')
