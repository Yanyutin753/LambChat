import pytest

from src.infra.model.config_storage import ModelConfigStorage
from src.kernel.config import settings


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    async def find_one(self, query):
        doc_type = query.get("type")
        return self._docs.get(doc_type)

    async def update_one(self, query, update, upsert=False):
        doc_type = query.get("type")
        existing = self._docs.get(doc_type, {"type": doc_type})
        existing.update(update.get("$set", {}))
        self._docs[doc_type] = existing


class _FakeStorage(ModelConfigStorage):
    def __init__(self, docs):
        super().__init__()
        self._docs = docs

    def _get_collection(self, name):
        return _FakeCollection(self._docs)


class _FakeSettingsService:
    def __init__(self, values):
        self._values = values

    async def get_raw(self, key):
        return self._values.get(key)


@pytest.mark.asyncio
async def test_legacy_global_migration_keeps_db_credentials(monkeypatch):
    storage = _FakeStorage(
        {
            "global": {
                "type": "global",
                "models": [
                    {
                        "id": "openai/gpt-4o",
                        "name": "GPT-4o",
                        "enabled": True,
                    }
                ],
            }
        }
    )

    monkeypatch.setattr(
        "src.infra.settings.service.get_settings_service",
        lambda: _FakeSettingsService(
            {
                "LLM_API_KEY": "legacy-db-key",
                "LLM_API_BASE": "https://legacy-db.example/v1",
            }
        ),
    )

    providers, metadata = await storage.get_provider_config_with_metadata(include_secrets=True)

    assert len(providers) == 1
    assert providers[0]["provider"] == "openai"
    assert providers[0]["api_key"] == "legacy-db-key"
    assert providers[0]["base_url"] == "https://legacy-db.example/v1"
    assert providers[0]["models"][0]["value"] == "openai/gpt-4o"
    assert metadata["legacy_migration_applied"] is True
    assert metadata["legacy_inherited_providers"] == ["openai"]
    assert storage._docs["providers"]["providers"][0]["provider"] == "openai"

    public_providers = await storage.get_provider_config()
    assert public_providers[0]["api_key"] is None
    assert public_providers[0]["has_api_key"] is True
    assert public_providers[0]["clear_api_key"] is False


@pytest.mark.asyncio
async def test_default_provider_config_keeps_db_credentials(monkeypatch):
    storage = _FakeStorage({})
    monkeypatch.setattr(settings, "LLM_MODEL", "openai/gpt-4o", raising=False)
    monkeypatch.setattr(settings, "LLM_AVAILABLE_MODELS", [], raising=False)
    monkeypatch.setattr(
        "src.infra.settings.service.get_settings_service",
        lambda: _FakeSettingsService(
            {
                "LLM_API_KEY": "legacy-db-key",
                "LLM_API_BASE": "https://legacy-db.example/v1",
            }
        ),
    )

    providers = await storage._build_provider_config_from_legacy_global(
        [{"id": "openai/gpt-4o", "name": "GPT-4o", "enabled": True}]
    )

    assert len(providers) == 1
    assert providers[0]["provider"] == "openai"
    assert providers[0]["api_key"] == "legacy-db-key"
    assert providers[0]["base_url"] == "https://legacy-db.example/v1"
    assert providers[0]["models"][0]["value"] == "openai/gpt-4o"


@pytest.mark.asyncio
async def test_set_provider_config_preserves_existing_api_key_when_omitted():
    storage = _FakeStorage({})

    await storage.set_provider_config(
        [
            {
                "provider": "openai",
                "label": "OpenAI",
                "api_key": "secret-key",
                "models": [{"value": "openai/gpt-4o", "label": "GPT-4o", "enabled": True}],
            }
        ]
    )

    await storage.set_provider_config(
        [
            {
                "provider": "openai",
                "label": "OpenAI Updated",
                "api_key": None,
                "has_api_key": True,
                "models": [{"value": "openai/gpt-4o", "label": "GPT-4o", "enabled": True}],
            }
        ]
    )

    raw_providers = await storage.get_provider_config_raw()
    assert raw_providers[0]["label"] == "OpenAI Updated"
    assert raw_providers[0]["api_key"] == "secret-key"

    public_providers = await storage.get_provider_config()
    assert public_providers[0]["api_key"] is None
    assert public_providers[0]["has_api_key"] is True


@pytest.mark.asyncio
async def test_set_provider_config_can_clear_existing_api_key():
    storage = _FakeStorage({})

    await storage.set_provider_config(
        [
            {
                "provider": "openai",
                "label": "OpenAI",
                "api_key": "secret-key",
                "models": [{"value": "openai/gpt-4o", "label": "GPT-4o", "enabled": True}],
            }
        ]
    )

    await storage.set_provider_config(
        [
            {
                "provider": "openai",
                "label": "OpenAI",
                "api_key": None,
                "clear_api_key": True,
                "models": [{"value": "openai/gpt-4o", "label": "GPT-4o", "enabled": True}],
            }
        ]
    )

    raw_providers = await storage.get_provider_config_raw()
    assert raw_providers[0]["api_key"] is None

    public_providers = await storage.get_provider_config()
    assert public_providers[0]["has_api_key"] is False
