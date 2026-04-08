import pytest

from src.api.routes.model import config as model_config_routes
from src.kernel.schemas.model import ModelConfig, ModelConfigUpdate
from src.kernel.schemas.user import TokenPayload


class _FakeModelStorage:
    def __init__(self, saved_configs=None, enabled_ids=None):
        self.saved_configs = saved_configs or []
        self.enabled_ids = enabled_ids or []
        self.saved_update = None

    async def get_global_config(self):
        return self.saved_configs

    async def set_global_config(self, models):
        self.saved_update = models
        self.saved_configs = models
        return models

    async def get_enabled_model_ids(self):
        return self.enabled_ids

    async def get_role_models(self, _role_id):
        return None


class _FakeRoleStorage:
    async def get_by_names(self, _role_names):
        return []


@pytest.mark.asyncio
async def test_update_global_model_config_accepts_registry_models_without_legacy_env(
    monkeypatch,
):
    storage = _FakeModelStorage()
    monkeypatch.setattr(model_config_routes, "get_model_config_storage", lambda: storage)
    monkeypatch.setattr(model_config_routes.settings, "LLM_AVAILABLE_MODELS", [])

    async def _publish(_event):
        return None

    monkeypatch.setattr("src.infra.model.pubsub.publish_model_config_change", _publish)
    monkeypatch.setattr("src.infra.llm.client.LLMClient.clear_cache_by_model", lambda: 0)

    response = await model_config_routes.update_global_model_config(
        ModelConfigUpdate(
            models=[
                ModelConfig(
                    id="glm-5.1",
                    name="GLM 5.1",
                    description="Registry-backed model",
                    enabled=True,
                )
            ]
        ),
        TokenPayload(sub="u1", username="tester", permissions=["model:admin"]),
    )

    assert response.available_models == ["glm-5.1"]
    assert storage.saved_update == [
        {
            "id": "glm-5.1",
            "name": "GLM 5.1",
            "description": "Registry-backed model",
            "enabled": True,
            "api_key": None,
            "api_base": None,
        }
    ]


@pytest.mark.asyncio
async def test_get_user_allowed_models_falls_back_to_registry_models(monkeypatch):
    storage = _FakeModelStorage(enabled_ids=[])
    monkeypatch.setattr(model_config_routes, "get_model_config_storage", lambda: storage)
    monkeypatch.setattr(model_config_routes, "RoleStorage", _FakeRoleStorage)
    monkeypatch.setattr(model_config_routes.settings, "LLM_AVAILABLE_MODELS", [])

    response = await model_config_routes.get_user_allowed_models(
        TokenPayload(sub="u1", username="tester", roles=[])
    )

    assert "glm-5.1" in response.models
