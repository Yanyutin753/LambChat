"""Model update route maps empty api_format back to the default (None)."""

from __future__ import annotations

import pytest

from src.api.routes.agent import model as model_routes
from src.kernel.schemas.model import ModelConfig, ModelConfigUpdate
from src.kernel.schemas.user import TokenPayload


class _FakeModelStorage:
    def __init__(self, model: ModelConfig) -> None:
        self.model = model
        self.updates: list[tuple[str, dict]] = []

    async def get(self, model_id: str) -> ModelConfig | None:
        return self.model if model_id == self.model.id else None

    async def update(self, model_id: str, update: dict) -> ModelConfig:
        self.updates.append((model_id, dict(update)))
        return ModelConfig(**{**self.model.model_dump(), **update})


async def _noop_invalidate() -> None:
    return None


def _admin_token() -> TokenPayload:
    return TokenPayload(sub="admin-1", username="admin", roles=["admin"])


@pytest.mark.asyncio
async def test_update_model_maps_empty_api_format_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ModelConfig(
        id="m1", value="openai/gpt-5.2", label="GPT", api_format="responses"
    )
    storage = _FakeModelStorage(model)
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: storage)
    monkeypatch.setattr(
        "src.infra.llm.models_service.invalidate_cache", _noop_invalidate
    )

    await model_routes.update_model("m1", ModelConfigUpdate(api_format=""), _admin_token())

    _, update = storage.updates[0]
    assert update["api_format"] is None


@pytest.mark.asyncio
async def test_update_model_keeps_explicit_api_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ModelConfig(id="m1", value="openai/gpt-5.2", label="GPT")
    storage = _FakeModelStorage(model)
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: storage)
    monkeypatch.setattr(
        "src.infra.llm.models_service.invalidate_cache", _noop_invalidate
    )

    await model_routes.update_model(
        "m1", ModelConfigUpdate(api_format="responses"), _admin_token()
    )

    _, update = storage.updates[0]
    assert update["api_format"] == "responses"
