"""Archive failures must not commit a summary that hides the original messages."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import FileUploadResponse
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from src.infra.agent.middleware.summary_fallback import summarization_fallback_patch
from src.kernel.errors import AppError, ErrorCode


def build(tmp_path):
    import deepagents.graph as graph

    backend = FilesystemBackend(tmp_path)
    model = GenericFakeChatModel(messages=iter([AIMessage("summary")] * 10))
    defaults = {"trigger": ("messages", 3), "keep": ("messages", 1), "truncate_args_settings": None}
    with patch(
        "deepagents.middleware.summarization.compute_summarization_defaults", return_value=defaults
    ):
        with summarization_fallback_patch(None):
            middleware = graph.create_summarization_middleware(model, backend)
    return middleware, backend, model


async def offload(middleware, backend, messages, sync):
    if sync:
        return await asyncio.to_thread(middleware._offload_to_backend, backend, messages, "history")
    return await middleware._aoffload_to_backend(backend, messages, "history")


@pytest.mark.parametrize("sync", [False, True])
async def test_archive_retries_transient_write_failure(tmp_path, monkeypatch, sync):
    middleware, backend, _ = build(tmp_path)
    original = backend.aupload_files
    calls = 0

    async def upload(files):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [FileUploadResponse(path=files[0][0], error="io_error")]
        return await original(files)

    monkeypatch.setattr(backend, "aupload_files", upload)
    path = await offload(middleware, backend, [HumanMessage("retain this decision")], sync)
    assert path and calls == 2
    assert next(tmp_path.rglob("*.md")).read_text().count("retain this decision") == 1


async def test_concurrent_archives_get_distinct_segments(tmp_path):
    middleware, backend, _ = build(tmp_path)
    paths = await asyncio.gather(
        *(
            offload(middleware, backend, [HumanMessage(text)], False)
            for text in ("first decision", "second decision")
        )
    )
    assert len(set(paths)) == 2
    for path, text in zip(paths, ("first decision", "second decision"), strict=True):
        assert text in (await backend.adownload_files([path]))[0].content.decode()


@pytest.mark.parametrize("disconnected", [False, True])
async def test_archive_retry_recognizes_committed_append_after_lost_response(
    tmp_path, monkeypatch, disconnected
):
    middleware, backend, _ = build(tmp_path)
    original = backend.aupload_files
    calls = 0

    async def upload(files):
        nonlocal calls
        calls += 1
        if calls > 1:
            return [FileUploadResponse(path=files[0][0], error="file_conflict")]
        await original(files)
        if disconnected:
            raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": 30})
        return [FileUploadResponse(path=files[0][0], error="io_error")]

    monkeypatch.setattr(backend, "aupload_files", upload)
    monkeypatch.setattr("src.infra.agent.middleware.summary_history.asyncio.sleep", AsyncMock())
    path = await middleware._aoffload_to_backend(backend, [HumanMessage("once only")], "history")
    assert path and calls == 2
    assert next(tmp_path.rglob("*.md")).read_text().count("once only") == 1


@pytest.mark.parametrize("sync", [False, True])
async def test_permanent_archive_failure_preserves_request_and_never_calls_main_model(
    tmp_path, monkeypatch, sync
):
    middleware, backend, model = build(tmp_path)
    write = AsyncMock(return_value=[FileUploadResponse(path="test", error="io_error")])
    monkeypatch.setattr(backend, "aupload_files", write)
    messages = [
        HumanMessage("important original"),
        AIMessage("decision"),
        HumanMessage("next"),
        AIMessage("evidence"),
        HumanMessage("continue"),
    ]
    state = {"messages": messages}
    request = ModelRequest(model=model, messages=messages, state=state, tools=[])
    handler = (
        Mock(return_value=ModelResponse(result=[AIMessage("continued")]))
        if sync
        else AsyncMock(return_value=ModelResponse(result=[AIMessage("continued")]))
    )
    with pytest.raises(AppError) as caught:
        if sync:
            await asyncio.to_thread(middleware.wrap_model_call, request, handler)
        else:
            await middleware.awrap_model_call(request, handler)
    assert caught.value.error_code.code == "conversation_history_save_failed"
    assert write.await_count == 3
    assert state == {"messages": messages} and request.messages == messages
    handler.assert_not_called()


async def test_archive_cancellation_is_not_retried(tmp_path, monkeypatch):
    middleware, backend, _ = build(tmp_path)
    write = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(backend, "aupload_files", write)
    with pytest.raises(asyncio.CancelledError):
        await middleware._aoffload_to_backend(backend, [HumanMessage("original")], "history")
    write.assert_awaited_once()


async def test_archive_failure_cancels_inflight_summary(tmp_path, monkeypatch):
    middleware, backend, model = build(tmp_path)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_summary(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def fail_write(*args):
        await started.wait()
        return [FileUploadResponse(path="test", error="io_error")]

    monkeypatch.setattr(type(model), "_agenerate", slow_summary)
    monkeypatch.setattr(backend, "aupload_files", fail_write)
    messages = [HumanMessage(str(i)) for i in range(5)]
    request = ModelRequest(model=model, messages=messages, state={"messages": messages}, tools=[])
    with pytest.raises(AppError):
        await asyncio.wait_for(middleware.awrap_model_call(request, AsyncMock()), 3)
    assert cancelled.is_set()


async def test_summary_failure_cancels_inflight_archive(tmp_path, monkeypatch):
    middleware, backend, model = build(tmp_path)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fail_summary(*args, **kwargs):
        await started.wait()
        raise ValueError("invalid summary input")

    async def slow_upload(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(type(model), "_agenerate", fail_summary)
    monkeypatch.setattr(type(model), "with_retry", lambda self, **kwargs: self)
    monkeypatch.setattr(backend, "aupload_files", slow_upload)
    messages = [HumanMessage(str(i)) for i in range(5)]
    request = ModelRequest(model=model, messages=messages, state={"messages": messages}, tools=[])
    with pytest.raises(ValueError, match="invalid summary input"):
        await asyncio.wait_for(middleware.awrap_model_call(request, AsyncMock()), 3)
    assert cancelled.is_set()


@pytest.mark.parametrize(
    "code", [ErrorCode.DAEMON_OFFLINE, ErrorCode.SANDBOX_MACHINE_OFFLINE, ErrorCode.SANDBOX_TIMEOUT]
)
@pytest.mark.parametrize("sync", [False, True])
async def test_archive_waits_for_local_reconnection_and_rechecks_history(
    tmp_path, monkeypatch, code, sync
):
    middleware, backend, _ = build(tmp_path)
    original = backend.aupload_files
    calls = 0

    async def upload(paths):
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise AppError(code, args={"machine": "same-machine", "seconds": 30})
        return await original(paths)

    monkeypatch.setattr(backend, "aupload_files", upload)
    monkeypatch.setattr("src.infra.agent.middleware.summary_history.asyncio.sleep", AsyncMock())
    path = await offload(middleware, backend, [HumanMessage("retained")], sync)
    assert path and calls == 4
    assert next(tmp_path.rglob("*.md")).read_text().count("retained") == 1


@pytest.mark.parametrize("stalled_read", [False, True])
async def test_archive_reconnection_deadline_preserves_offline_error_and_original_context(
    tmp_path, monkeypatch, stalled_read
):
    middleware, backend, model = build(tmp_path)
    offline = AppError(ErrorCode.SANDBOX_MACHINE_OFFLINE, args={"machine": "same-machine"})
    calls = 0

    async def upload(*args):
        nonlocal calls
        calls += 1
        if stalled_read and calls > 1:
            await asyncio.Event().wait()
        raise offline

    monkeypatch.setattr(backend, "aupload_files", upload)
    monkeypatch.setattr("src.infra.agent.middleware.summary_history._RECONNECT_TIMEOUT", 0.01)
    if stalled_read:
        monkeypatch.setattr("src.infra.agent.middleware.summary_history.asyncio.sleep", AsyncMock())
    messages = [HumanMessage(f"original {i}") for i in range(5)]
    state = {"messages": messages}
    request = ModelRequest(model=model, messages=messages, state=state, tools=[])
    handler = AsyncMock()
    with pytest.raises(AppError) as caught:
        await asyncio.wait_for(middleware.awrap_model_call(request, handler), 2)
    assert caught.value is offline
    assert state == {"messages": messages} and request.messages == messages
    handler.assert_not_called()


async def test_archive_reconnection_can_be_cancelled_without_another_attempt(tmp_path, monkeypatch):
    middleware, backend, _ = build(tmp_path)
    started = asyncio.Event()

    async def upload(*args):
        started.set()
        raise AppError(ErrorCode.DAEMON_OFFLINE)

    upload_mock = AsyncMock(side_effect=upload)
    monkeypatch.setattr(backend, "aupload_files", upload_mock)
    task = asyncio.create_task(offload(middleware, backend, [HumanMessage("retained")], False))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    upload_mock.assert_awaited_once()


async def test_large_compaction_writes_bounded_ordered_segments(tmp_path, monkeypatch):
    from langchain_core.messages import get_buffer_string

    from src.infra.agent.middleware import summary_history

    middleware, backend, _ = build(tmp_path)
    monkeypatch.setattr(summary_history, "_SEGMENT_CHARS", 128)
    messages = [HumanMessage(f"{i}: " + "多<&" * 80) for i in range(7)]
    last = await offload(middleware, backend, messages, False)
    parts = sorted(tmp_path.rglob("*.md"))
    assert len(parts) > 1 and parts[-1] == tmp_path / last.lstrip("/")
    texts = [p.read_text() for p in parts]
    assert all(len(text) <= 128 for text in texts)
    assert "".join(texts).split("\n\n", 1)[1] == get_buffer_string(messages, format="xml") + "\n\n"
