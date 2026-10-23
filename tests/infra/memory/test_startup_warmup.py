import asyncio
from unittest.mock import AsyncMock

import pytest

from src.infra.memory import tools as memory_tools
from src.kernel.config import settings


async def test_memory_warmup_initializes_clients_without_recall_or_embedding(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    backend = AsyncMock()
    get_backend = AsyncMock(return_value=backend)
    monkeypatch.setattr(memory_tools, "_get_backend", get_backend)
    from src.infra.memory.client.native import vector_store

    get_index = AsyncMock()
    monkeypatch.setattr(vector_store, "get_vector_index", get_index)
    await memory_tools.warmup_backend()
    get_backend.assert_awaited_once()
    get_index.assert_awaited_once()
    backend.recall.assert_not_awaited()
    backend._maybe_embed.assert_not_awaited()


async def test_disabled_memory_warmup_performs_no_initialization(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_MEMORY", False)
    get_backend = AsyncMock()
    monkeypatch.setattr(memory_tools, "_get_backend", get_backend)
    await memory_tools.warmup_backend()
    get_backend.assert_not_awaited()


@pytest.mark.parametrize("error", [RuntimeError("offline"), asyncio.CancelledError()])
async def test_interrupted_backend_initialization_closes_its_clients(monkeypatch, error):
    from src.infra.memory.client import base, native

    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    backend = AsyncMock()
    backend.initialize.side_effect = error
    monkeypatch.setattr(native, "NativeMemoryBackend", lambda: backend)
    if isinstance(error, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await base.create_memory_backend()
    else:
        assert await base.create_memory_backend() is None
    backend.close.assert_awaited_once()


async def test_memory_warmup_failure_is_nonfatal_but_cancellation_propagates(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    get_backend = AsyncMock(side_effect=RuntimeError("unavailable"))
    monkeypatch.setattr(memory_tools, "_get_backend", get_backend)
    await memory_tools.warmup_backend()
    get_backend.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await memory_tools.warmup_backend()


async def test_worker_tracks_memory_preparation_and_cancels_it_on_exit(monkeypatch):
    from src.infra.async_utils import loop_bridge
    from src.infra.task import arq_worker

    monkeypatch.setattr(arq_worker, "validate_distributed_runtime_settings", lambda _: None)
    monkeypatch.setattr(arq_worker, "_schedule_model_warmup", lambda: None)
    monkeypatch.setattr(loop_bridge, "set_main_loop", lambda _: None)
    monkeypatch.setattr(loop_bridge, "clear_main_loop", lambda: None)
    monkeypatch.setattr("src.infra.task.lifecycle.mark_shutting_down", lambda: None)
    started = asyncio.Event()

    async def warmup():
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(memory_tools, "warmup_backend", warmup)
    ctx = {}
    await arq_worker.worker_startup(ctx)
    assert "memory_warmup_task" in ctx
    task = ctx["memory_warmup_task"]
    await asyncio.wait_for(started.wait(), 1)
    await arq_worker.worker_shutdown(ctx)
    assert task.cancelled()
