from __future__ import annotations

from typing import Any

import pytest

from src.kernel.config import SETTING_DEFINITIONS


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = docs or []
        self.length = None

    async def to_list(self, length=None):
        self.length = length
        return self.docs


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs_by_id = {doc["_id"]: doc for doc in docs or []}
        self.cursor = _FakeCursor(list(self.docs_by_id.values()))
        self.find_calls = []
        self.find_one_calls = []

    def find(self, query, projection=None):
        self.find_calls.append((query, projection))
        return self.cursor

    async def find_one(self, query):
        self.find_one_calls.append(query)
        return self.docs_by_id.get(query.get("_id"))


@pytest.mark.asyncio
async def test_get_all_bounds_settings_query() -> None:
    from src.infra.settings.storage import SettingsStorage

    collection = _FakeCollection()
    storage = SettingsStorage()
    storage._collection = collection

    await storage.get_all(admin_mode=True)

    assert collection.cursor.length == len(SETTING_DEFINITIONS)
    query, projection = collection.find_calls[0]
    assert query == {"_id": {"$in": list(SETTING_DEFINITIONS.keys())}}
    assert projection == {
        "_id": 1,
        "value": 1,
        "updated_at": 1,
        "updated_by": 1,
    }


@pytest.mark.asyncio
async def test_settings_storage_close_clears_local_client_reference() -> None:
    from src.infra.settings.storage import SettingsStorage

    storage = SettingsStorage()
    storage._client = object()
    storage._collection = _FakeCollection()

    await storage.close()

    assert storage._client is None
    assert storage._collection is None


@pytest.mark.asyncio
async def test_get_all_hides_plugin_owned_legacy_settings_but_raw_keeps_migration_access() -> None:
    from src.infra.settings.storage import SettingsStorage

    collection = _FakeCollection(
        [
            {"_id": "IMAGE_GENERATION_API_KEY", "value": "sk-legacy"},
            {"_id": "AUDIO_TRANSCRIPTION_API_KEY", "value": "sk-audio"},
        ]
    )
    storage = SettingsStorage()
    storage._collection = collection

    grouped = await storage.get_all(admin_mode=True, mask_sensitive=False)
    visible_keys = {item.key for items in grouped.values() for item in items}

    assert "IMAGE_GENERATION_API_KEY" not in visible_keys
    assert "AUDIO_TRANSCRIPTION_API_KEY" not in visible_keys
    assert await storage.get("IMAGE_GENERATION_API_KEY") is None

    raw = await storage.get_raw("IMAGE_GENERATION_API_KEY")
    assert raw is not None
    assert raw.value == "sk-legacy"


@pytest.mark.asyncio
async def test_settings_service_get_offloads_env_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.settings import service as service_module
    from src.infra.settings.service import SettingsService

    inside_blocking_io = False

    class _NoDbSettingStorage:
        async def get(self, _key: str) -> None:
            return None

    async def fake_run_blocking_io(func, /, *args: Any, **kwargs: Any) -> Any:
        nonlocal inside_blocking_io
        assert inside_blocking_io is False
        inside_blocking_io = True
        try:
            return func(*args, **kwargs)
        finally:
            inside_blocking_io = False

    def fake_json_loads(value: str) -> dict[str, Any]:
        assert inside_blocking_io, "JSON environment setting parsing must be offloaded"
        assert value == '{"en":[]}'
        return {"en": []}

    monkeypatch.setenv("WELCOME_SUGGESTIONS", '{"en":[]}')
    monkeypatch.setattr(service_module, "run_blocking_io", fake_run_blocking_io)
    monkeypatch.setattr(service_module.json, "loads", fake_json_loads)

    settings_service = SettingsService()
    settings_service._storage = _NoDbSettingStorage()  # type: ignore[assignment]

    value = await settings_service.get("WELCOME_SUGGESTIONS")

    assert value == {"en": []}
