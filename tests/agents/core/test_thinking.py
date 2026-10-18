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


def test_execution_default_only_applies_when_user_option_is_missing():
    assert build_thinking_config(None, default_level="medium") == {
        "type": "enabled",
        "level": "medium",
        "budget_tokens": 8192,
    }
    assert build_thinking_config({}, default_level="medium")["level"] == "medium"
    for selected in ("low", False, "off", None, "invalid"):
        options = {"enable_thinking": selected}
        assert build_thinking_config(options, default_level="medium")["level"] == "low"
        assert options == {"enable_thinking": selected}
    assert (
        build_thinking_config({"enable_thinking": "max"}, default_level="medium")["level"] == "max"
    )


async def test_agent_entry_defaults_match_catalog_without_promoting_explicit_low(monkeypatch):
    import pytest

    from src.agents.quick_agent import nodes as quick_nodes
    from src.agents.search_agent import nodes as search_nodes
    from src.agents.search_agent.graph import SearchAgent
    from src.agents.team_agent import nodes as team_nodes
    from src.agents.team_agent.graph import TeamAgent

    class CapturedThinkingError(Exception):
        def __init__(self, config):
            self.config = config

    def capture(options, **kwargs):
        raise CapturedThinkingError(build_thinking_config(options, **kwargs))

    for agent_cls in (SearchAgent, TeamAgent):
        assert agent_cls._options["enable_thinking"]["default"] == "medium"
    for module, node, default in (
        (search_nodes, search_nodes.agent_node, "medium"),
        (team_nodes, team_nodes.team_router_node, "medium"),
        (quick_nodes, quick_nodes.quick_agent_node, "low"),
    ):
        monkeypatch.setattr(module, "build_thinking_config", capture)
        if hasattr(module, "get_presenter"):
            monkeypatch.setattr(module, "get_presenter", lambda _config: object())
        for options, expected in (({}, default), ({"enable_thinking": "low"}, "low")):
            with pytest.raises(CapturedThinkingError) as captured:
                await node({}, {"configurable": {"agent_options": options}})
            assert captured.value.config["level"] == expected
