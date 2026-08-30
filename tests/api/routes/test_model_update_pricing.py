"""模型配置价格覆盖字段：schema 透传 + 清空语义 + 创建透传。"""

from __future__ import annotations

import pytest

from src.api.routes.agent import model as model_routes
from src.kernel.schemas.model import ModelConfig, ModelConfigCreate, ModelConfigUpdate
from src.kernel.schemas.user import TokenPayload


class _FakeModelStorage:
    def __init__(self, model: ModelConfig | None = None) -> None:
        self.model = model
        self.updates: list[tuple[str, dict]] = []
        self.created: list[dict] = []

    async def get(self, model_id: str) -> ModelConfig | None:
        return self.model if model_id == self.model.id else None

    async def update(self, model_id: str, update: dict) -> ModelConfig:
        self.updates.append((model_id, dict(update)))
        return ModelConfig(**{**self.model.model_dump(), **update})

    async def create(self, model: ModelConfig) -> ModelConfig:
        self.created.append(model.model_dump())
        return model


async def _noop_invalidate() -> None:
    return None


def _admin_token() -> TokenPayload:
    return TokenPayload(sub="admin-1", username="admin", roles=["admin"])


class TestModelPricingOverrideSchema:
    def test_config_holds_pricing_override(self):
        model = ModelConfig(
            id="m1",
            value="relay/custom",
            label="Relay",
            pricing={"input": 1.5, "output": 6.0, "cache_read": 0.2, "cache_write": 1.875},
        )
        assert model.pricing is not None
        assert model.pricing.input == 1.5
        assert model.pricing.cache_write == 1.875

    def test_pricing_defaults_to_none(self):
        model = ModelConfig(id="m1", value="gpt-4o", label="GPT")
        assert model.pricing is None


@pytest.mark.asyncio
async def test_update_model_persists_pricing_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ModelConfig(id="m1", value="relay/custom", label="Relay")
    storage = _FakeModelStorage(model)
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: storage)
    monkeypatch.setattr("src.infra.llm.models_service.invalidate_cache", _noop_invalidate)

    await model_routes.update_model(
        "m1",
        ModelConfigUpdate(pricing={"input": 1.5, "output": 6.0}),
        _admin_token(),
    )

    _, update = storage.updates[0]
    assert update["pricing"] == {"input": 1.5, "output": 6.0}


@pytest.mark.asyncio
async def test_update_model_maps_empty_pricing_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ModelConfig(
        id="m1",
        value="relay/custom",
        label="Relay",
        pricing={"input": 1.5, "output": 6.0},
    )
    storage = _FakeModelStorage(model)
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: storage)
    monkeypatch.setattr("src.infra.llm.models_service.invalidate_cache", _noop_invalidate)

    await model_routes.update_model("m1", ModelConfigUpdate(pricing={}), _admin_token())

    _, update = storage.updates[0]
    assert update["pricing"] is None


@pytest.mark.asyncio
async def test_create_model_carries_pricing_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeModelStorage()
    monkeypatch.setattr(model_routes, "get_model_storage", lambda: storage)
    monkeypatch.setattr("src.infra.llm.models_service.invalidate_cache", _noop_invalidate)

    await model_routes.create_model(
        ModelConfigCreate(
            value="relay/custom",
            label="Relay",
            pricing={"input": 1.0, "output": 2.0},
        ),
        _admin_token(),
    )

    created_pricing = storage.created[0]["pricing"]
    assert created_pricing["input"] == 1.0
    assert created_pricing["output"] == 2.0
