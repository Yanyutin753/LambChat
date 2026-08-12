from pathlib import Path

from src.kernel.config import settings
from src.kernel.config.definitions import SETTING_DEFINITIONS, SettingCategory, SettingType


def test_llm_request_timeout_is_an_admin_setting() -> None:
    definition = SETTING_DEFINITIONS["LLM_REQUEST_TIMEOUT"]

    assert settings.LLM_REQUEST_TIMEOUT == 120.0
    assert definition["type"] == SettingType.NUMBER
    assert definition["category"] == SettingCategory.LLM
    assert definition["subcategory"] == "retry"
    assert definition["default"] == 120.0


def test_llm_timing_settings_invalidate_cached_models() -> None:
    source = Path("src/kernel/config/service.py").read_text()

    assert '"LLM_REQUEST_TIMEOUT"' in source
    assert '"LLM_RETRY_DELAY"' in source
