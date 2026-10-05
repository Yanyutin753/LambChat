"""Shared httpx connection pools for the LLM model cache.

The model cache is keyed by the full parameter set (temperature, thinking,
profile, …), so one provider with several parameter combinations occupies
several cache slots — each holding its own httpx connection pool that gets
rebuilt whenever the 50-slot LRU churns. Only connection-relevant fields
(api_key / api_base) actually determine the underlying HTTP connection, so
models with identical connection fields must share one pooled
httpx.AsyncClient; parameter differences stay on the (cheap) model instances.
"""

import asyncio

import pytest

from src.infra.llm import httpx_pool
from src.infra.llm.client import LLMClient
from src.infra.llm.httpx_pool import (
    _httpx_pool_cache,
    _httpx_pool_refs,
    _model_pool_keys,
    _pool_key,
    _release_pool_client,
    _retired_pools,
    _retired_sdk_clients,
    release_all_pooled_clients,
)
from src.kernel.schemas.model import ModelConfig

_POOL_BASE = "https://relay.example.com/v1"


def _clear_pool_state() -> None:
    LLMClient._model_cache.clear()
    _httpx_pool_cache.clear()
    _httpx_pool_refs.clear()
    _model_pool_keys.clear()
    for entry in _retired_pools.values():
        if entry.timer is not None:
            entry.timer.cancel()
    _retired_pools.clear()
    for entry in _retired_sdk_clients.values():
        if entry.timer is not None:
            entry.timer.cancel()
    _retired_sdk_clients.clear()


@pytest.fixture(autouse=True)
def _isolate_model_cache():
    _clear_pool_state()
    yield
    _clear_pool_state()


def _config(
    api_key: str = "sk-pool",
    api_base: str = "https://relay.example.com/v1",
    temperature: float | None = None,
) -> ModelConfig:
    return ModelConfig(
        value="openai/gpt-test",
        label="test",
        api_key=api_key,
        api_base=api_base,
        temperature=temperature,
    )


def _underlying_async_client(model):
    client = model.root_async_client
    return getattr(client, "_client", None) or client


@pytest.mark.asyncio
async def test_same_connection_fields_share_httpx_pool_across_temperatures() -> None:
    warm = await LLMClient.get_model(model_config=_config(temperature=0.2))
    hot = await LLMClient.get_model(model_config=_config(temperature=0.9), temperature=0.9)

    # Distinct model instances preserving each temperature…
    assert warm is not hot
    assert warm.temperature == 0.2
    assert hot.temperature == 0.9
    # …sharing the same underlying httpx connection pool.
    assert _underlying_async_client(warm) is _underlying_async_client(hot)


@pytest.mark.asyncio
async def test_different_api_key_gets_distinct_httpx_pool() -> None:
    first = await LLMClient.get_model(model_config=_config(api_key="sk-one"))
    second = await LLMClient.get_model(model_config=_config(api_key="sk-two"))

    assert _underlying_async_client(first) is not _underlying_async_client(second)


@pytest.mark.asyncio
async def test_identical_params_still_return_cached_instance() -> None:
    one = await LLMClient.get_model(model_config=_config())
    two = await LLMClient.get_model(model_config=_config())
    assert one is two


@pytest.mark.asyncio
async def test_last_reference_retires_pool_instead_of_closing(monkeypatch) -> None:
    """清缓存把引用归零时只退役不立刻关闭——在途 run 仍持有被逐出实例。"""
    monkeypatch.setattr(httpx_pool, "_close_grace_seconds", lambda: 60.0)
    model = await LLMClient.get_model(model_config=_config())
    client = _underlying_async_client(model)
    key = _pool_key("sk-pool", _POOL_BASE)
    assert _httpx_pool_refs[key] == 1

    LLMClient._model_cache.clear()
    _release_pool_client(key, model)
    assert _httpx_pool_refs.get(key) is None
    await asyncio.sleep(0)  # 让（错误的）立即关闭任务有机会执行
    assert not client.is_closed
    assert key in _retired_pools


@pytest.mark.asyncio
async def test_retired_pool_is_revived_on_reacquire(monkeypatch) -> None:
    """宽限期内重新 acquire 同一连接键，必须复用同一个池化客户端。"""
    monkeypatch.setattr(httpx_pool, "_close_grace_seconds", lambda: 60.0)
    model = await LLMClient.get_model(model_config=_config())
    client = _underlying_async_client(model)
    key = _pool_key("sk-pool", _POOL_BASE)

    LLMClient._model_cache.clear()
    _release_pool_client(key, model)

    revived_model = await LLMClient.get_model(
        model_config=_config(temperature=0.7), temperature=0.7
    )
    assert _underlying_async_client(revived_model) is client
    assert key not in _retired_pools
    assert not client.is_closed


@pytest.mark.asyncio
async def test_retired_pool_closes_after_grace_expiry(monkeypatch) -> None:
    """宽限期到后仍无新引用，退役池真正关闭（不泄漏连接）。"""
    monkeypatch.setattr(httpx_pool, "_close_grace_seconds", lambda: 0.05)
    model = await LLMClient.get_model(model_config=_config())
    client = _underlying_async_client(model)
    key = _pool_key("sk-pool", _POOL_BASE)

    LLMClient._model_cache.clear()
    _release_pool_client(key, model)
    assert not client.is_closed

    await asyncio.sleep(0.15)
    await LLMClient.drain_close_tasks()
    assert client.is_closed


@pytest.mark.asyncio
async def test_evicted_model_keeps_pool_usable(monkeypatch) -> None:
    """被逐出的 openai 协议实例：池子退役期间 SDK wrapper 不得关闭共享池。"""
    monkeypatch.setattr(httpx_pool, "_close_grace_seconds", lambda: 60.0)
    model = await LLMClient.get_model(model_config=_config())
    client = _underlying_async_client(model)

    httpx_pool._evict_model_instance(model)
    await asyncio.sleep(0)
    assert not client.is_closed


@pytest.mark.asyncio
async def test_safe_close_client_defers_non_pooled_sdk_close(monkeypatch) -> None:
    """非池化 SDK wrapper（anthropic/google 协议）逐出后也走宽限，不立即关闭。"""
    monkeypatch.setattr(httpx_pool, "_close_grace_seconds", lambda: 60.0)

    class _FakeSDK:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeModel:
        def __init__(self) -> None:
            self.async_client = _FakeSDK()

    fake = _FakeModel()
    httpx_pool._safe_close_client(fake)
    await asyncio.sleep(0)
    assert not fake.async_client.closed


@pytest.mark.asyncio
async def test_deferred_sdk_close_fires_after_grace(monkeypatch) -> None:
    monkeypatch.setattr(httpx_pool, "_close_grace_seconds", lambda: 0.05)

    class _FakeSDK:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeModel:
        def __init__(self) -> None:
            self.async_client = _FakeSDK()

    fake = _FakeModel()
    httpx_pool._safe_close_client(fake)
    await asyncio.sleep(0.15)
    await LLMClient.drain_close_tasks()
    assert fake.async_client.closed


@pytest.mark.asyncio
async def test_release_all_pooled_clients_flushes_immediately(monkeypatch) -> None:
    """停机 flush：活跃池、退役池、待关 SDK wrapper 一律立即关闭，不等宽限。"""
    monkeypatch.setattr(httpx_pool, "_close_grace_seconds", lambda: 60.0)

    class _FakeSDK:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class _FakeModel:
        def __init__(self) -> None:
            self.async_client = _FakeSDK()

    active_model = await LLMClient.get_model(model_config=_config(api_key="sk-active"))
    retired_model = await LLMClient.get_model(model_config=_config(api_key="sk-retired"))
    active_client = _underlying_async_client(active_model)
    retired_client = _underlying_async_client(retired_model)
    retired_key = _pool_key("sk-retired", _POOL_BASE)

    LLMClient._model_cache.clear()
    _release_pool_client(retired_key, retired_model)  # 进入退役宽限
    fake = _FakeModel()
    httpx_pool._safe_close_client(fake)  # 非池化 deferral

    release_all_pooled_clients()
    await LLMClient.drain_close_tasks()
    assert active_client.is_closed
    assert retired_client.is_closed
    assert fake.async_client.closed
