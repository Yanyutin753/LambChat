from src.kernel.config._definitions_extra import EXTRA_SETTING_DEFINITIONS
from src.kernel.config.base import Settings
from src.kernel.config.service import _normalize_runtime_setting


def test_hitl_defaults_to_interrupt_only() -> None:
    assert Settings().HITL_MODE == "interrupt"
    definition = EXTRA_SETTING_DEFINITIONS["HITL_MODE"]
    assert definition["default"] == "interrupt"
    assert definition["options"] == ["interrupt"]


def test_legacy_blocking_value_is_normalized_to_interrupt() -> None:
    assert _normalize_runtime_setting("HITL_MODE", "blocking") == "interrupt"
