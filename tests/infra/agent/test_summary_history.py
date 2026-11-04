"""Archive failures must not commit a summary that hides the original messages."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import FileDownloadResponse, WriteResult
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
    original = backend.write
    calls = 0

    async def write(path, content):
        nonlocal calls
        calls += 1
        if calls == 1:
            return WriteResult(error="temporary storage failure")
        return await asyncio.to_thread(original, path, content)

    monkeypatch.setattr(backend, "awrite", write)
    monkeypatch.setattr(
        backend, "write", Mock(return_value=WriteResult(error="temporary storage failure"))
    )
    path = await offload(middleware, backend, [HumanMessage("retain this decision")], sync)
    assert path and calls == 2
    assert next(tmp_path.rglob("*.md")).read_text().count("retain this decision") == 1


async def test_archive_rereads_after_unknown_download_error_without_overwriting(
    tmp_path, monkeypatch
):
    middleware, backend, _ = build(tmp_path)
    path = await middleware._aoffload_to_backend(
        backend, [HumanMessage("first decision")], "history"
    )
    original = backend.adownload_files
    calls = 0

    async def download(paths):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [FileDownloadResponse(path=paths[0], error="io_error")]
        return await original(paths)

    monkeypatch.setattr(backend, "adownload_files", download)
    await middleware._aoffload_to_backend(backend, [HumanMessage("next decision")], "history")
    content = (await original([path]))[0].content.decode()
    assert calls == 2
    assert content.count("first decision") == content.count("next decision") == 1


async def test_archive_retry_recognizes_a_committed_write_after_lost_response(
    tmp_path, monkeypatch
):
    middleware, backend, _ = build(tmp_path)
    original = backend.awrite
    calls = 0

    async def write(path, content):
        nonlocal calls
        calls += 1
        await original(path, content)
        return WriteResult(error="response lost after commit")

    monkeypatch.setattr(backend, "awrite", write)
    path = await middleware._aoffload_to_backend(backend, [HumanMessage("once only")], "history")
    assert path and calls == 1
    assert next(tmp_path.rglob("*.md")).read_text().count("once only") == 1


@pytest.mark.parametrize("disconnected", [False, True])
async def test_archive_retry_recognizes_committed_append_after_lost_response(
    tmp_path, monkeypatch, disconnected
):
    from deepagents.backends.protocol import EditResult

    middleware, backend, _ = build(tmp_path)
    original = backend.aedit
    calls = 0

    async def edit(*args):
        nonlocal calls
        calls += 1
        await original(*args)
        if disconnected:
            raise AppError(ErrorCode.SANDBOX_TIMEOUT, args={"seconds": 30})
        return EditResult(error="response lost after commit")

    monkeypatch.setattr(backend, "aedit", edit)
    monkeypatch.setattr("src.infra.agent.middleware.summary_history.asyncio.sleep", AsyncMock())
    path = await middleware._aoffload_to_backend(backend, [HumanMessage("once only")], "history")
    assert path and calls == 1
    assert next(tmp_path.rglob("*.md")).read_text().count("once only") == 1


async def test_archive_initialization_does_not_allow_summary_when_append_fails(
    tmp_path, monkeypatch
):
    from deepagents.backends.protocol import EditResult

    middleware, backend, model = build(tmp_path)
    edit = AsyncMock(return_value=EditResult(error="storage unavailable"))
    monkeypatch.setattr(backend, "aedit", edit)
    messages = [HumanMessage(f"original {i}") for i in range(5)]
    state = {"messages": messages}
    request = ModelRequest(model=model, messages=messages, state=state, tools=[])
    handler = AsyncMock()
    with pytest.raises(AppError):
        await middleware.awrap_model_call(request, handler)
    assert edit.await_count == 3
    assert state == {"messages": messages} and request.messages == messages
    handler.assert_not_called()


@pytest.mark.parametrize("sync", [False, True])
async def test_permanent_archive_failure_preserves_request_and_never_calls_main_model(
    tmp_path, monkeypatch, sync
):
    middleware, backend, model = build(tmp_path)
    write = AsyncMock(return_value=WriteResult(error="storage unavailable"))
    monkeypatch.setattr(backend, "awrite", write)
    monkeypatch.setattr(
        backend, "write", Mock(return_value=WriteResult(error="storage unavailable"))
    )
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
    monkeypatch.setattr(backend, "awrite", write)
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
        return WriteResult(error="storage unavailable")

    monkeypatch.setattr(type(model), "_agenerate", slow_summary)
    monkeypatch.setattr(backend, "awrite", fail_write)
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

    async def slow_download(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(type(model), "_agenerate", fail_summary)
    monkeypatch.setattr(type(model), "with_retry", lambda self, **kwargs: self)
    monkeypatch.setattr(backend, "adownload_files", slow_download)
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
    original = backend.adownload_files
    calls = 0

    async def download(paths):
        nonlocal calls
        calls += 1
        if calls <= 3:
            raise AppError(code, args={"machine": "same-machine", "seconds": 30})
        return await original(paths)

    monkeypatch.setattr(backend, "adownload_files", download)
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

    async def download(*args):
        nonlocal calls
        calls += 1
        if stalled_read and calls > 1:
            await asyncio.Event().wait()
        raise offline

    monkeypatch.setattr(backend, "adownload_files", download)
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

    async def download(*args):
        started.set()
        raise AppError(ErrorCode.DAEMON_OFFLINE)

    download_mock = AsyncMock(side_effect=download)
    monkeypatch.setattr(backend, "adownload_files", download_mock)
    task = asyncio.create_task(offload(middleware, backend, [HumanMessage("retained")], False))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    download_mock.assert_awaited_once()
