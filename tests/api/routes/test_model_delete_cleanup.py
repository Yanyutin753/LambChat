from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.api.routes.agent import model as model_routes
from src.kernel.schemas.model import ModelConfig
from src.kernel.schemas.user import TokenPayload


class _FakeCollection:
    async def update_many(self, _query: dict, _update: dict) -> SimpleNamespace:
        return SimpleNamespace(modified_count=0)


class _FakeModelStorage:
    def __init__(
        self,
        model: ModelConfig,
        *,
        remaining_by_value: ModelConfig | None = None,
    ) -> None:
        self.model = model
        self.remaining_by_value = remaining_by_value
        self.deleted_ids: list[str] = []
        self.collection = _FakeCollection()

    async def get(self, model_id: str) -> ModelConfig | None:
        return self.model if model_id == self.model.id else None

    async def delete(self, model_id: str) -> bool:
        self.deleted_ids.append(model_id)
        return True

    async def get_by_value(self, _model_value: str) -> ModelConfig | None:
        return self.remaining_by_value

    def _get_collection(self) -> _FakeCollection:
        return self.collection


class _FakeSettingsService:
    def __init__(self, reference: str) -> None:
        self.values = {"NATIVE_MEMORY_COMPACTION_MODEL_ID": reference}
        self.updated_by: str | None = None

    async def get_raw(self, key: str) -> str:
        return self.values[key]

    async def set(self, key: str, value: str, user_id: str) -> SimpleNamespace:
        self.values[key] = value
        self.updated_by = user_id
        return SimpleNamespace(key=key, value=value)


class _FakeAgentStorage:
    async def remove_model_from_all_roles(self, _model_id: str) -> int:
        return 0


def _admin_token() -> TokenPayload:
    return TokenPayload(sub="admin-1", username="admin", roles=["admin"])


def _install_delete_route_fakes(
    monkeypatch: pytest.MonkeyPatch,
    storage: _FakeModelStorage,
    settings_service: _FakeSettingsService,
    invalidations: list[str] | None = None,
) -> None:
    async def _invalidate_cache() -> None:
        if invalidations is not None:
            invalidations.append("invalidated")

    monkeypatch.setattr(model_routes, "get_model_storage", lambda: storage)
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _FakeAgentStorage(),
    )
    monkeypatch.setattr(
        "src.infra.settings.service.get_settings_service",
        lambda: settings_service,
    )
    monkeypatch.setattr("src.infra.llm.models_service.invalidate_cache", _invalidate_cache)


@pytest.mark.asyncio
@pytest.mark.parametrize("reference", ["model-id", "openai/deleted-model"])
async def test_delete_model_clears_matching_compaction_reference(
    monkeypatch: pytest.MonkeyPatch,
    reference: str,
) -> None:
    model = ModelConfig(id="model-id", value="openai/deleted-model", label="Deleted")
    storage = _FakeModelStorage(model)
    settings_service = _FakeSettingsService(reference)
    _install_delete_route_fakes(monkeypatch, storage, settings_service)

    await model_routes.delete_model("model-id", _admin_token())

    assert storage.deleted_ids == ["model-id"]
    assert settings_service.values["NATIVE_MEMORY_COMPACTION_MODEL_ID"] == ""
    assert settings_service.updated_by == "system:model-delete"


@pytest.mark.asyncio
async def test_delete_model_preserves_unrelated_compaction_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ModelConfig(id="model-id", value="openai/deleted-model", label="Deleted")
    storage = _FakeModelStorage(model)
    settings_service = _FakeSettingsService("other-model")
    _install_delete_route_fakes(monkeypatch, storage, settings_service)

    await model_routes.delete_model("model-id", _admin_token())

    assert storage.deleted_ids == ["model-id"]
    assert settings_service.values["NATIVE_MEMORY_COMPACTION_MODEL_ID"] == "other-model"
    assert settings_service.updated_by is None


@pytest.mark.asyncio
async def test_delete_model_preserves_value_reference_when_duplicate_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ModelConfig(id="model-id", value="openai/shared-model", label="Deleted")
    remaining = ModelConfig(id="model-id-2", value="openai/shared-model", label="Remaining")
    storage = _FakeModelStorage(model, remaining_by_value=remaining)
    settings_service = _FakeSettingsService("openai/shared-model")
    _install_delete_route_fakes(monkeypatch, storage, settings_service)

    await model_routes.delete_model("model-id", _admin_token())

    assert storage.deleted_ids == ["model-id"]
    assert settings_service.values["NATIVE_MEMORY_COMPACTION_MODEL_ID"] == "openai/shared-model"
    assert settings_service.updated_by is None


@pytest.mark.asyncio
async def test_delete_model_invalidates_cache_when_setting_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingSettingsService(_FakeSettingsService):
        async def get_raw(self, key: str) -> str:
            raise RuntimeError("settings unavailable")

    model = ModelConfig(id="model-id", value="openai/deleted-model", label="Deleted")
    storage = _FakeModelStorage(model)
    settings_service = _FailingSettingsService("model-id")
    invalidations: list[str] = []
    _install_delete_route_fakes(monkeypatch, storage, settings_service, invalidations)

    with pytest.raises(RuntimeError, match="settings unavailable"):
        await model_routes.delete_model("model-id", _admin_token())

    assert storage.deleted_ids == ["model-id"]
    assert invalidations == ["invalidated"]
