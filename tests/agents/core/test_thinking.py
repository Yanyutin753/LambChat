from src.agents.core.thinking import build_thinking_config, normalize_thinking_level


def test_build_thinking_config_normalizes_off_aliases_to_low() -> None:
    # "off" 档已下线：思考常开，历史 off 值（含旧布尔 false）统一降级到最低档
    low = {"type": "enabled", "level": "low", "budget_tokens": 1024}
    assert build_thinking_config({"enable_thinking": False}) == low
    assert build_thinking_config({"enable_thinking": "off"}) == low
    assert build_thinking_config({"enable_thinking": "none"}) == low
    assert build_thinking_config({"enable_thinking": "disabled"}) == low


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


def test_normalize_thinking_level_maps_off_aliases_to_low() -> None:
    assert normalize_thinking_level("off") == "low"
    assert normalize_thinking_level(False) == "low"
    assert normalize_thinking_level("none") == "low"
    assert normalize_thinking_level("disabled") == "low"
