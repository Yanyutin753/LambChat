import pytest

from src.infra.model.config_storage import ModelConfigStorage


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    async def find_one(self, query):
        doc_type = query.get("type") or query.get("role_id")
        if "role_id" in query:
            for doc in self._docs.values():
                if doc.get("role_id") == doc_type:
                    return doc
            return None
        return self._docs.get(doc_type)

    async def update_one(self, query, update, upsert=False):
        doc_type = query.get("type") or query.get("role_id")
        if "role_id" in query:
            existing = None
            for key, doc in self._docs.items():
                if doc.get("role_id") == doc_type:
                    existing = doc
                    break
            if existing is None:
                existing = {"role_id": doc_type}
                self._docs[doc_type] = existing
            existing.update(update.get("$set", {}))
        else:
            existing = self._docs.get(doc_type, {"type": doc_type})
            existing.update(update.get("$set", {}))
            self._docs[doc_type] = existing

    async def delete_one(self, query):
        role_id = query.get("role_id")
        for key, doc in list(self._docs.items()):
            if doc.get("role_id") == role_id:
                del self._docs[key]
                return type("Result", (), {"deleted_count": 1})()
        return type("Result", (), {"deleted_count": 0})()

    def find(self, *_args, **_kwargs):
        return self

    async def to_list(self, length):
        return list(self._docs.values())[:length]

    def __aiter__(self):
        return iter(self._docs.values())


class _FakeStorage(ModelConfigStorage):
    def __init__(self, docs):
        super().__init__()
        self._docs = docs

    def _get_collection(self, name):
        return _FakeCollection(self._docs)


@pytest.mark.asyncio
async def test_global_config_round_trip():
    storage = _FakeStorage({})

    models = await storage.set_global_config(
        [{"id": "openai/gpt-4o", "name": "GPT-4o", "enabled": True}]
    )

    assert len(models) == 1
    assert models[0]["id"] == "openai/gpt-4o"

    result = await storage.get_global_config()
    assert len(result) == 1
    assert result[0]["id"] == "openai/gpt-4o"


@pytest.mark.asyncio
async def test_get_enabled_model_ids_filters_disabled():
    storage = _FakeStorage(
        {
            "global": {
                "type": "global",
                "models": [
                    {"id": "openai/gpt-4o", "name": "GPT-4o", "enabled": True},
                    {"id": "anthropic/claude-3", "name": "Claude 3", "enabled": False},
                ],
            }
        }
    )

    enabled = await storage.get_enabled_model_ids()
    assert enabled == ["openai/gpt-4o"]


@pytest.mark.asyncio
async def test_providers_round_trip():
    storage = _FakeStorage({})

    providers = await storage.set_providers(
        [
            {
                "name": "openai",
                "api_key": "secret-key",
                "api_base": "https://api.openai.com/v1",
                "enabled": True,
            }
        ]
    )

    assert len(providers) == 1

    result = await storage.get_providers()
    assert result[0]["name"] == "openai"
    assert result[0]["api_key"] == "secret-key"


@pytest.mark.asyncio
async def test_get_provider_credentials_returns_credentials_for_enabled_provider():
    storage = _FakeStorage(
        {
            "providers": {
                "type": "providers",
                "providers": [
                    {
                        "name": "openai",
                        "api_key": "sk-test",
                        "api_base": "https://api.openai.com/v1",
                        "enabled": True,
                    }
                ],
            }
        }
    )

    creds = await storage.get_provider_credentials("openai")
    assert creds["api_key"] == "sk-test"
    assert creds["api_base"] == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_get_provider_credentials_returns_none_for_unknown_provider():
    storage = _FakeStorage({})

    creds = await storage.get_provider_credentials("unknown")
    assert creds["api_key"] is None
    assert creds["api_base"] is None


@pytest.mark.asyncio
async def test_role_models_round_trip():
    storage = _FakeStorage({})

    model_ids = await storage.set_role_models("role-1", "Admin", ["openai/gpt-4o"])
    assert model_ids == ["openai/gpt-4o"]

    result = await storage.get_role_models("role-1")
    assert result == ["openai/gpt-4o"]


@pytest.mark.asyncio
async def test_get_role_models_returns_none_for_unconfigured_role():
    storage = _FakeStorage({})

    result = await storage.get_role_models("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_delete_role_models():
    storage = _FakeStorage(
        {"role-1": {"role_id": "role-1", "role_name": "Admin", "allowed_models": ["openai/gpt-4o"]}}
    )

    deleted = await storage.delete_role_models("role-1")
    assert deleted is True

    result = await storage.get_role_models("role-1")
    assert result is None
