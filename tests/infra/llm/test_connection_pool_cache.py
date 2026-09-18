"""Shared httpx connection pools for the LLM model cache.

The model cache is keyed by the full parameter set (temperature, thinking,
profile, …), so one provider with several parameter combinations occupies
several cache slots — each holding its own httpx connection pool that gets
rebuilt whenever the 50-slot LRU churns. Only connection-relevant fields
(api_key / api_base) actually determine the underlying HTTP connection, so
models with identical connection fields must share one pooled
httpx.AsyncClient; parameter differences stay on the (cheap) model instances.
"""

import pytest

from src.infra.llm.client import LLMClient
from src.infra.llm.httpx_pool import (
    _httpx_pool_cache,
    _httpx_pool_refs,
    _model_pool_keys,
    _pool_key,
    _release_pool_client,
)
from src.kernel.schemas.model import ModelConfig


def _clear_pool_state() -> None:
    LLMClient._model_cache.clear()
    _httpx_pool_cache.clear()
    _httpx_pool_refs.clear()
    _model_pool_keys.clear()


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
async def test_pool_client_not_closed_while_cached_models_reference_it() -> None:
    model = await LLMClient.get_model(model_config=_config())
    client = _underlying_async_client(model)
    key = _pool_key("sk-pool", "https://relay.example.com/v1")
    assert _httpx_pool_refs[key] == 1

    # Dropping the cached model releases the pool entry; the last reference
    # gone closes the pooled client (no leak).
    LLMClient._model_cache.clear()
    _release_pool_client(key, model)
    assert _httpx_pool_refs.get(key) is None
    await LLMClient.drain_close_tasks()
    assert client.is_closed
