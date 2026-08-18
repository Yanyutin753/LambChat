from src.agents.core.thinking import build_thinking_config, normalize_thinking_level


def test_build_thinking_config_returns_disabled_dict_when_off() -> None:
    disabled = {"type": "disabled", "level": "off", "budget_tokens": 0}
    assert build_thinking_config({"enable_thinking": False}) == disabled
    assert build_thinking_config({"enable_thinking": "off"}) == disabled
    assert build_thinking_config({"enable_thinking": "none"}) == disabled
    assert build_thinking_config({"enable_thinking": "disabled"}) == disabled


def test_build_thinking_config_defaults_to_low_when_missing() -> None:
    low = {"type": "enabled", "level": "low", "budget_tokens": 1024}
    assert build_thinking_config({}) == low
    assert build_thinking_config(None) == low
    assert build_thinking_config({"enable_thinking": None}) == low
    assert build_thinking_config({"enable_thinking": "bogus-value"}) == low


def test_build_thinking_config_maps_legacy_boolean_to_medium() -> None:
    assert build_thinking_config({"enable_thinking": True}) == {
        "type": "enabled",
        "level": "medium",
        "budget_tokens": 8192,
    }


def test_build_thinking_config_maps_supported_levels() -> None:
    assert build_thinking_config({"enable_thinking": "low"}) == {
        "type": "enabled",
        "level": "low",
        "budget_tokens": 1024,
    }
    assert build_thinking_config({"enable_thinking": "medium"}) == {
        "type": "enabled",
        "level": "medium",
        "budget_tokens": 8192,
    }
    assert build_thinking_config({"enable_thinking": "high"}) == {
        "type": "enabled",
        "level": "high",
        "budget_tokens": 32768,
    }
    assert build_thinking_config({"enable_thinking": "max"}) == {
        "type": "enabled",
        "level": "max",
        "budget_tokens": 65536,
    }


def test_normalize_thinking_level_defaults_to_low() -> None:
    assert normalize_thinking_level(None) == "low"
    assert normalize_thinking_level("unknown") == "low"


def test_normalize_thinking_level_keeps_explicit_off() -> None:
    assert normalize_thinking_level("off") == "off"
    assert normalize_thinking_level(False) == "off"
    assert normalize_thinking_level("none") == "off"
    assert normalize_thinking_level("disabled") == "off"
