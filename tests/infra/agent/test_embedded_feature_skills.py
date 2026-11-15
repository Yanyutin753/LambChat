from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.infra.agent.middleware.embedded_feature_skills import EmbeddedFeatureSkillsMiddleware


def computer_skill(selection):
    selection = selection or {}
    return EmbeddedFeatureSkillsMiddleware(
        capabilities={"local_computer"}
        if selection.get("platform") == "local" and selection.get("machine_id")
        else set(),
        platform=selection.get("os_platform", ""),
    )


@dataclass
class Request:
    messages: list
    tools: list
    system_message: SystemMessage

    def override(self, **kwargs):
        return replace(self, **kwargs)


async def identity(request):
    return request


def request(tools=True):
    return Request(
        [HumanMessage(content="Fill the open form")],
        [SimpleNamespace(name="computer_use")] if tools else [],
        SystemMessage(content="Original system prompt"),
    )


@pytest.mark.parametrize(
    "platform, heading, absent",
    [
        ("win32", "Windows", "## macOS"),
        ("darwin", "macOS", "## Windows"),
        ("linux", "Linux", "## Windows"),
    ],
)
async def test_builtin_skill_is_platform_specific_runtime_context_not_a_system_prompt(
    platform, heading, absent
):
    source = request()
    middleware = computer_skill(
        selection={"platform": "local", "machine_id": "owned", "os_platform": platform}
    )
    result = await middleware.awrap_model_call(source, identity)
    assert result.system_message is source.system_message
    assert result.tools is source.tools
    assert len(source.messages) == 1
    assert result.messages[1:] == source.messages
    skill = result.messages[0]
    assert skill.name == "embedded_feature_skill"
    assert skill.additional_kwargs["feature_skill_id"] == "computer-use"
    assert skill.additional_kwargs["lambchat_builtin_skill"] is True
    assert f"## {heading}" in skill.content
    assert absent not in skill.content
    assert "owned" not in skill.content
    assert "delivery" in skill.content


@pytest.mark.parametrize(
    "selection, tools",
    [
        (None, True),
        ({"platform": "cloud", "machine_id": "cloud"}, True),
        ({"platform": "local", "machine_id": None}, True),
        ({"platform": "local", "machine_id": "owned"}, False),
    ],
)
async def test_unavailable_or_unauthorized_computer_never_loads_skill(selection, tools):
    source = request(tools)
    result = await computer_skill(selection=selection).awrap_model_call(source, identity)
    assert result is source


async def test_unknown_platform_cannot_choose_an_arbitrary_resource_path():
    result = await computer_skill(
        selection={"platform": "local", "machine_id": "owned", "os_platform": "../../secrets"}
    ).awrap_model_call(request(), identity)
    assert "platform is unknown" in result.messages[0].content
    assert "../../secrets" not in result.messages[0].content


async def test_skill_is_not_duplicated_and_original_user_text_is_preserved():
    middleware = computer_skill(
        selection={"platform": "local", "machine_id": "owned", "os_platform": "win32"}
    )
    source = request()
    source.messages.append(
        HumanMessage(
            content="Quoted computer_use_skill instructions", name="embedded_feature_skill"
        )
    )
    first = await middleware.awrap_model_call(source, identity)
    second = await middleware.awrap_model_call(first, identity)
    assert len(second.messages) == 3
    assert second.messages[1:] == source.messages


async def test_tool_revocation_removes_only_previous_internal_skill_context():
    middleware = computer_skill(
        selection={"platform": "local", "machine_id": "owned", "os_platform": "win32"}
    )
    first = await middleware.awrap_model_call(request(), identity)
    revoked = await middleware.awrap_model_call(first.override(tools=[]), identity)
    assert len(revoked.messages) == 1
    assert revoked.messages[0].content == "Fill the open form"


async def test_real_model_request_keeps_checkpoint_and_system_unchanged():
    from langchain.agents.middleware.types import ModelRequest
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    history = [HumanMessage(content="Read the selected app")]
    state = {"messages": history}
    system = SystemMessage(content="Original policy")
    source = ModelRequest(
        model=FakeListChatModel(responses=["ok"]),
        messages=history,
        system_message=system,
        state=state,
        tools=[{"name": "computer_use"}],
    )
    result = await computer_skill(
        selection={"platform": "local", "machine_id": "mac", "os_platform": "darwin"},
    ).awrap_model_call(source, identity)
    assert result.state is state
    assert result.state["messages"] is history
    assert len(history) == 1
    assert result.system_message is system
    assert result.messages[1:] == history


async def test_new_features_share_loader_and_require_actual_tools_and_capabilities(
    tmp_path, monkeypatch
):
    from src.infra.skill.builtin import catalog

    (tmp_path / "SKILL.md").write_text("Feature A embedded guide", encoding="utf-8")
    definition = catalog.BuiltinFeatureSkill(
        id="feature-a",
        directory=tmp_path,
        required_tools=frozenset({"a_read", "a_write"}),
        required_capabilities=frozenset({"feature_a_enabled"}),
    )
    monkeypatch.setattr(catalog, "BUILTIN_FEATURE_SKILLS", (definition,))
    source = request().override(tools=[{"name": "a_read"}, {"name": "a_write"}])
    disabled = EmbeddedFeatureSkillsMiddleware()
    assert await disabled.awrap_model_call(source, identity) is source
    enabled = EmbeddedFeatureSkillsMiddleware(capabilities={"feature_a_enabled"})
    result = await enabled.awrap_model_call(source, identity)
    assert result.messages[0].additional_kwargs["feature_skill_id"] == "feature-a"
    assert "Feature A embedded guide" in result.messages[0].content
    assert result.system_message is source.system_message
    limited = source.override(tools=[{"name": "a_read"}])
    assert await enabled.awrap_model_call(limited, identity) is limited


@pytest.mark.parametrize("invalid", ["duplicate", "no_tools", "outside_bundle"])
async def test_invalid_bundled_feature_registration_fails_explicitly(
    tmp_path, monkeypatch, invalid
):
    from src.infra.skill.builtin import catalog

    (tmp_path / "SKILL.md").write_text("Guide", encoding="utf-8")
    definition = catalog.BuiltinFeatureSkill(
        id="a",
        directory=tmp_path,
        required_tools=frozenset() if invalid == "no_tools" else frozenset({"a"}),
        platform_files=(("win32", "../outside.md"),) if invalid == "outside_bundle" else (),
    )
    monkeypatch.setattr(
        catalog,
        "BUILTIN_FEATURE_SKILLS",
        (definition, definition) if invalid == "duplicate" else (definition,),
    )
    with pytest.raises(ValueError):
        middleware = EmbeddedFeatureSkillsMiddleware(platform="win32")
        await middleware.awrap_model_call(request().override(tools=[{"name": "a"}]), identity)


async def test_multiple_features_are_stable_and_revocation_removes_only_affected_guide(
    tmp_path, monkeypatch
):
    from src.infra.skill.builtin import catalog

    (tmp_path / "SKILL.md").write_text("Guide", encoding="utf-8")
    monkeypatch.setattr(
        catalog,
        "BUILTIN_FEATURE_SKILLS",
        tuple(
            catalog.BuiltinFeatureSkill(
                id=name, directory=tmp_path, required_tools=frozenset({name})
            )
            for name in ("b", "a")
        ),
    )
    middleware = EmbeddedFeatureSkillsMiddleware()
    source = request().override(tools=[{"name": "a"}, {"name": "b"}])
    first = await middleware.awrap_model_call(source, identity)
    repeated = await middleware.awrap_model_call(first, identity)
    assert repeated.messages == first.messages
    assert [m.additional_kwargs["feature_skill_id"] for m in first.messages[:2]] == ["b", "a"]
    revoked = await middleware.awrap_model_call(first.override(tools=[{"name": "a"}]), identity)
    assert len(revoked.messages) == 2
    assert revoked.messages[0].additional_kwargs["feature_skill_id"] == "a"
    assert revoked.messages[1:] == source.messages


async def test_provider_function_schema_is_recognized_without_accepting_malformed_names():
    middleware = computer_skill({"platform": "local", "machine_id": "mac"})
    source = request().override(
        tools=[
            {"type": "function", "function": {"name": "computer_use"}},
            {"name": ["not-a-name"]},
        ]
    )
    result = await middleware.awrap_model_call(source, identity)
    assert result.messages[0].additional_kwargs["feature_skill_id"] == "computer-use"


async def test_unavailable_feature_does_not_load_its_resources(tmp_path, monkeypatch):
    from src.infra.skill.builtin import catalog

    monkeypatch.setattr(
        catalog,
        "BUILTIN_FEATURE_SKILLS",
        (
            catalog.BuiltinFeatureSkill(
                id="unused",
                directory=tmp_path / "not-installed",
                required_tools=frozenset({"unused"}),
            ),
        ),
    )
    middleware = EmbeddedFeatureSkillsMiddleware()
    source = request()
    assert await middleware.awrap_model_call(source, identity) is source


@pytest.mark.parametrize("enabled", [False, True])
async def test_shared_runtime_assembly_preserves_feature_toggle_and_trusted_platform(
    monkeypatch, enabled
):
    from unittest.mock import AsyncMock

    from src.agents.core.node_utils import prepare_runtime_feature_skills
    from src.infra.tool import computer_use_tool as cut

    selection = {"platform": "local", "machine_id": "selected", "os_platform": "win32"}
    resolve = AsyncMock(return_value=selection)
    monkeypatch.setattr(cut, "resolve_computer_use_context", resolve)
    options = {"sandbox": "local"}
    resume = {"confirmation_context": {"machine_id": "selected"}}
    context, middleware = await prepare_runtime_feature_skills(
        "owner",
        options,
        resume,
        computer_use_enabled=enabled,
    )
    source = request()
    result = await middleware.awrap_model_call(source, identity)
    if enabled:
        resolve.assert_awaited_once_with("owner", options, resume)
        assert context is selection
        assert "## Windows" in result.messages[0].content
    else:
        resolve.assert_not_called()
        assert context is None
        assert result is source
