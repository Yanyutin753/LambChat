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
    storage.get = AsyncMock(return_value=db_model)
    storage.get_by_value = AsyncMock(return_value=db_model)

    if db_fallback is not None:

        async def get(key):
            if db_model is not None and key == db_model.id:
                return db_model
            return db_fallback

        storage.get = AsyncMock(side_effect=get)

    with patch(
        "src.infra.agent.model_storage.get_model_storage", return_value=storage
    ):
        result = await resolve_fallback_model(
            "m1" if db_model else None,
            db_model.value if db_model else "primary-model",
        )

    assert result == expected
