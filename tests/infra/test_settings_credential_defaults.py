"""Credential defaults must be masked as carefully as current values."""

from types import SimpleNamespace

import pytest

from src.infra.settings import storage as settings_storage
from src.kernel.schemas.setting import SettingCategory, SettingType


@pytest.fixture
def credential_storage(monkeypatch):
    definitions = {
        "TEST_SECRET": {
            "type": SettingType.STRING,
            "category": SettingCategory.SECURITY,
            "description": "Secret",
            "is_sensitive": True,
            "frontend_visible": False,
        }
    }
    monkeypatch.setattr(settings_storage, "SETTING_DEFINITIONS", definitions)
    monkeypatch.setattr(
        settings_storage, "_get_default_from_settings", lambda *args: "private-configured-default"
    )
    storage = settings_storage.SettingsStorage()

    class Cursor:
        async def to_list(self, length):
            return []

    monkeypatch.setattr(
        storage, "_get_collection", lambda: SimpleNamespace(find=lambda *args: Cursor())
    )
    return storage


async def test_grouped_settings_do_not_expose_sensitive_defaults(credential_storage):
    grouped = await credential_storage.get_all(admin_mode=True)
    item = grouped["security"][0]
    assert item.value == "********"
    assert item.default_value == "********"
    assert "private-configured-default" not in item.model_dump_json()


def test_single_setting_does_not_expose_sensitive_defaults(credential_storage):
    item = credential_storage._item_from_doc("TEST_SECRET", None)
    assert item.value == "********"
    assert item.default_value == "********"
    internal = credential_storage._item_from_doc("TEST_SECRET", None, mask_sensitive=False)
    assert internal.value == "private-configured-default"
