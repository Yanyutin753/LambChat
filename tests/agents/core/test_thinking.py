from src.agents.core.thinking import build_thinking_config


def test_build_thinking_config_returns_none_when_disabled() -> None:
    assert build_thinking_config({"enable_thinking": False}) is None
    assert build_thinking_config({"enable_thinking": "off"}) is None
    assert build_thinking_config({}) is None


def test_build_thinking_config_maps_legacy_boolean_to_medium() -> None:
    assert build_thinking_config({"enable_thinking": True}) == {
        "type": "enabled",
        "level": "medium",
    }


def test_build_thinking_config_maps_supported_levels() -> None:
    assert build_thinking_config({"enable_thinking": "low"}) == {
        "type": "enabled",
        "level": "low",
    }
    assert build_thinking_config({"enable_thinking": "medium"}) == {
        "type": "enabled",
        "level": "medium",
    }
    assert build_thinking_config({"enable_thinking": "high"}) == {
        "type": "enabled",
        "level": "high",
    }
    assert build_thinking_config({"enable_thinking": "max"}) == {
        "type": "enabled",
        "level": "max",
    }
