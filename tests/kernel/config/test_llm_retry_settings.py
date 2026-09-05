from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.kernel.config import service as config_service
from src.kernel.config import settings
from src.kernel.config.base import Settings
from src.kernel.config.definitions import SETTING_DEFINITIONS, SettingCategory, SettingType


def test_llm_timeout_settings_are_admin_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    request_definition = SETTING_DEFINITIONS["LLM_REQUEST_TIMEOUT"]
    first_event_definition = SETTING_DEFINITIONS["LLM_FIRST_EVENT_TIMEOUT"]
    stream_idle_definition = SETTING_DEFINITIONS["LLM_STREAM_IDLE_TIMEOUT"]

    # 本地 .env 可能覆盖 LLM_* 超时；用纯净实例校验 base 默认值本身
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT", raising=False)
    monkeypatch.delenv("LLM_FIRST_EVENT_TIMEOUT", raising=False)
    monkeypatch.delenv("LLM_STREAM_IDLE_TIMEOUT", raising=False)
    pristine = Settings(_env_file=None)

    assert pristine.LLM_REQUEST_TIMEOUT == 0.0
    assert pristine.LLM_FIRST_EVENT_TIMEOUT == 30.0
    assert pristine.LLM_STREAM_IDLE_TIMEOUT == 120.0
    for definition in (request_definition, first_event_definition, stream_idle_definition):
        assert definition["type"] == SettingType.NUMBER
        assert definition["category"] == SettingCategory.LLM
        assert definition["subcategory"] == "retry"
    assert request_definition["default"] == 0.0
    assert first_event_definition["default"] == 30.0
    assert stream_idle_definition["default"] == 120.0


@pytest.mark.parametrize(
    "key",
    ["LLM_REQUEST_TIMEOUT", "LLM_FIRST_EVENT_TIMEOUT", "LLM_STREAM_IDLE_TIMEOUT"],
)
async def test_llm_timing_setting_updates_invalidate_cached_models(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
) -> None:
    value = 45.0 if key == "LLM_REQUEST_TIMEOUT" else 15.0

    class _Storage:
        async def get_raw(self, requested_key: str):
            assert requested_key == key
            return SimpleNamespace(value=value)

    monkeypatch.setattr(config_service, "_settings_service", SimpleNamespace(_storage=_Storage()))
    monkeypatch.setattr(settings, key, getattr(settings, key))
    clear_cache = Mock(return_value=2)
    monkeypatch.setattr("src.infra.llm.client.LLMClient.clear_cache_by_model", clear_cache)

    await config_service.refresh_settings(key)

    assert getattr(settings, key) == value
    clear_cache.assert_called_once_with()


def test_llm_timeout_configuration_is_documented() -> None:
    env_example = Path(".env.example").read_text()
    en_docs = Path("docs/en/env/llm.md").read_text()
    zh_docs = Path("docs/zh/env/llm.md").read_text()

    assert "LLM_REQUEST_TIMEOUT=0" in env_example
    assert "LLM_FIRST_EVENT_TIMEOUT=30" in env_example
    assert "LLM_STREAM_IDLE_TIMEOUT=120" in env_example
    assert "LLM_FIRST_EVENT_TIMEOUT" in en_docs
    assert "first provider event" in en_docs
    assert "LLM_STREAM_IDLE_TIMEOUT" in en_docs
    assert "streaming chunks" in en_docs
    assert "LLM_FIRST_EVENT_TIMEOUT" in zh_docs
    assert "首个 provider 事件" in zh_docs
    assert "LLM_STREAM_IDLE_TIMEOUT" in zh_docs
    assert "相邻 chunk" in zh_docs
