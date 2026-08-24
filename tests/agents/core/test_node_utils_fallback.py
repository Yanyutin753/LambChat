"""Tests for global fallback model resolution in resolve_fallback_model."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.core.node_utils import resolve_fallback_model


@pytest.mark.parametrize(
    ("db_model", "db_fallback", "global_fallback", "expected"),
    [
        # DB fallback wins over global default
        (
            SimpleNamespace(id="m1", fallback_model="fb1", value="primary-model"),
            SimpleNamespace(label="FB", value="db-fallback-model"),
            "global-fallback-model",
            "db-fallback-model",
        ),
        # No DB fallback configured -> global default used
        (
            SimpleNamespace(id="m1", fallback_model=None, value="primary-model"),
            None,
            "global-fallback-model",
            "global-fallback-model",
        ),
        # No DB fallback, no global default -> None
        (
            SimpleNamespace(id="m1", fallback_model=None, value="primary-model"),
            None,
            None,
            None,
        ),
        # No DB record at all -> global default used
        (None, None, "global-fallback-model", "global-fallback-model"),
        # Global default equal to the selected model itself -> None (no self-fallback)
        (
            SimpleNamespace(id="m1", fallback_model=None, value="primary-model"),
            None,
            "primary-model",
            None,
        ),
    ],
)
async def test_resolve_fallback_model_global_default(
    monkeypatch, db_model, db_fallback, global_fallback, expected
):
    monkeypatch.setattr("src.kernel.config.settings.LLM_FALLBACK_MODEL", global_fallback)

    storage = SimpleNamespace()
    storage.get_by_value = AsyncMock(return_value=db_model)

    async def get(key):
        if db_model is not None and key == db_model.id:
            return db_model
        if db_fallback is not None:
            return db_fallback
        return None

    storage.get = AsyncMock(side_effect=get)

    with patch("src.infra.agent.model_storage.get_model_storage", return_value=storage):
        result = await resolve_fallback_model(
            "m1" if db_model else None,
            db_model.value if db_model else "primary-model",
        )

    assert result == expected


# ── 全局兜底设置存模型配置 UUID（前端下拉保存 id）───────────────────────────


async def test_global_fallback_resolves_model_config_id_to_value(monkeypatch):
    monkeypatch.setattr("src.kernel.config.settings.LLM_FALLBACK_MODEL", "fb-uuid-1")
    db_model = SimpleNamespace(id="m1", fallback_model=None, value="primary-model")
    fb_model = SimpleNamespace(id="fb-uuid-1", label="FB", value="uuid-fallback-model")

    storage = SimpleNamespace()

    async def get(key):
        if key == "m1":
            return db_model
        if key == "fb-uuid-1":
            return fb_model
        return None

    storage.get = AsyncMock(side_effect=get)
    storage.get_by_value = AsyncMock(return_value=db_model)

    with patch("src.infra.agent.model_storage.get_model_storage", return_value=storage):
        result = await resolve_fallback_model("m1", "primary-model")

    assert result == "uuid-fallback-model"


async def test_global_fallback_uuid_pointing_at_primary_is_skipped(monkeypatch):
    monkeypatch.setattr("src.kernel.config.settings.LLM_FALLBACK_MODEL", "m1")
    db_model = SimpleNamespace(id="m1", fallback_model=None, value="primary-model")

    storage = SimpleNamespace()

    async def get(key):
        return db_model if key == "m1" else None

    storage.get = AsyncMock(side_effect=get)
    storage.get_by_value = AsyncMock(return_value=db_model)

    with patch("src.infra.agent.model_storage.get_model_storage", return_value=storage):
        result = await resolve_fallback_model("m1", "primary-model")

    assert result is None


async def test_global_fallback_storage_error_keeps_raw_value(monkeypatch):
    """storage.get 抛错（如旧 value 非 ObjectId）时按原始字符串兜底。"""
    monkeypatch.setattr("src.kernel.config.settings.LLM_FALLBACK_MODEL", "global-fallback-model")
    db_model = SimpleNamespace(id="m1", fallback_model=None, value="primary-model")

    storage = SimpleNamespace()

    async def get(key):
        if key == "m1":
            return db_model
        raise ValueError("InvalidId")

    storage.get = AsyncMock(side_effect=get)
    storage.get_by_value = AsyncMock(return_value=db_model)

    with patch("src.infra.agent.model_storage.get_model_storage", return_value=storage):
        result = await resolve_fallback_model("m1", "primary-model")

    assert result == "global-fallback-model"
