from __future__ import annotations

import json
from typing import Any

import pytest

from src.infra.llm import models_service
from src.infra.storage import redis as redis_storage
from src.kernel.config import settings


@pytest.fixture(autouse=True)
def clear_model_caches() -> None:
    models_service.clear_memory_cache()
    models_service.clear_api_key_cache()


@pytest.mark.asyncio
async def test_get_default_model_prefers_admin_default_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEFAULT_MODEL_ID", "model-b", raising=False)

    async def fake_get_available_models() -> list[dict[str, str]]:
        return [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "anthropic/claude-b"},
        ]

    monkeypatch.setattr(models_service, "get_available_models", fake_get_available_models)

    assert await models_service.get_default_model() == "anthropic/claude-b"
    assert await models_service.get_default_model_id() == "model-b"


@pytest.mark.asyncio
async def test_get_default_model_falls_back_when_admin_default_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEFAULT_MODEL_ID", "missing-model", raising=False)

    async def fake_get_available_models() -> list[dict[str, str]]:
        return [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "anthropic/claude-b"},
        ]

    monkeypatch.setattr(models_service, "get_available_models", fake_get_available_models)

    assert await models_service.get_default_model() == "openai/gpt-a"
    assert await models_service.get_default_model_id() == "model-a"


@pytest.mark.asyncio
async def test_get_default_model_respects_allowed_models_before_admin_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEFAULT_MODEL_ID", "model-b", raising=False)

    async def fake_get_available_models() -> list[dict[str, str]]:
        return [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "anthropic/claude-b"},
        ]

    monkeypatch.setattr(models_service, "get_available_models", fake_get_available_models)

    assert await models_service.get_default_model(["model-a"]) == "openai/gpt-a"
    assert await models_service.get_default_model_id(["model-a"]) == "model-a"


@pytest.mark.asyncio
async def test_resolve_model_reference_prefers_model_config_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_available_models() -> list[dict[str, str]]:
        return [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "anthropic/claude-b"},
        ]

    monkeypatch.setattr(models_service, "get_available_models", fake_get_available_models)

    assert await models_service.resolve_model_reference("model-b") == (
        "model-b",
        None,
    )


@pytest.mark.asyncio
async def test_resolve_model_reference_keeps_legacy_model_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_available_models() -> list[dict[str, str]]:
        return [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "anthropic/claude-b"},
        ]

    monkeypatch.setattr(models_service, "get_available_models", fake_get_available_models)

    assert await models_service.resolve_model_reference("anthropic/claude-b") == (
        None,
        "anthropic/claude-b",
    )


@pytest.mark.asyncio
async def test_resolve_model_reference_empty_uses_default_model() -> None:
    assert await models_service.resolve_model_reference("") == (None, None)


def test_set_memory_cache_caps_cached_model_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(models_service, "_MODELS_CACHE_MAX_SIZE", 2)

    models_service.set_memory_cache(
        [
            {"id": "model-a", "value": "openai/gpt-a"},
            {"id": "model-b", "value": "openai/gpt-b"},
            {"id": "model-c", "value": "openai/gpt-c"},
        ]
    )

    assert models_service._memory_cache == [
        {"id": "model-a", "value": "openai/gpt-a"},
        {"id": "model-b", "value": "openai/gpt-b"},
    ]


class _RecordingRedis:
    def __init__(self, cached: str | None = None) -> None:
        self.cached = cached
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, _key: str):
        return self.cached

    async def set(self, key: str, value: str, ex: int | None = None):
        self.set_calls.append((key, value, ex))


@pytest.mark.asyncio
async def test_get_available_models_offloads_redis_cache_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    cached = '[{"id": "model-a", "value": "openai/gpt-a"}]'
    redis = _RecordingRedis(cached=cached)

    async def _fake_run_long_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "get_redis_client", lambda: redis)
    monkeypatch.setattr(
        models_service, "run_long_blocking_io", _fake_run_long_blocking_io, raising=False
    )

    result = await models_service.get_available_models()

    assert calls == [json.loads]
    assert result == [{"id": "model-a", "value": "openai/gpt-a"}]


@pytest.mark.asyncio
async def test_write_to_caches_offloads_redis_cache_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    redis = _RecordingRedis()

    async def _fake_run_long_blocking_io(func, /, *args: Any, **kwargs: Any):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(redis_storage, "get_redis_client", lambda: redis)
    monkeypatch.setattr(
        models_service, "run_long_blocking_io", _fake_run_long_blocking_io, raising=False
    )

    await models_service._write_to_caches(
        [{"id": "model-a", "value": "openai/gpt-a", "api_key": "secret"}]
    )

    assert calls == [json.dumps]
    assert redis.set_calls == [
        (
            models_service._MODELS_CACHE_KEY,
            '[{"id": "model-a", "value": "openai/gpt-a", "api_key": null}]',
            models_service._MODELS_CACHE_TTL,
        )
    ]
