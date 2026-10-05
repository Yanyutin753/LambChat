"""Per-channel execution settings never expose secrets in task options."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.channel.runtime import (
    build_channel_agent_options,
    build_channel_session_metadata,
    normalize_runtime_config,
)


def test_session_metadata_persists_non_secret_run_options_and_explicit_project_clear():
    options = {
        "sandbox": "local",
        "channel_runtime": {"instance_id": "one", "channel_type": "telegram"},
    }
    metadata = build_channel_session_metadata(
        agent_id="search",
        agent_options=options,
        project_id=None,
        team_id=None,
        enabled_skills=["one"],
        enabled_mcp_servers=["mcp"],
        persona_system_prompt="persona",
        auto_mode=False,
    )
    assert metadata["agent_options"] == options
    assert "project_id" in metadata and metadata["project_id"] is None
    assert metadata["enabled_mcp_servers"] == ["mcp"]
    assert metadata["persona_snapshot"]["system_prompt"] == "persona"
    assert metadata["executor_key"] == "agent_stream"


def test_masked_environment_values_are_preserved_but_removed_keys_are_deleted():
    old = {"env_vars": {"API_KEY": "secret", "OLD": "remove"}, "sandbox": "local"}
    result = normalize_runtime_config({"env_vars": {"API_KEY": "***", "NEW": "value"}}, old)
    assert result["env_vars"] == {"API_KEY": "secret", "NEW": "value"}
    assert result["sandbox"] == "local"
    assert old["env_vars"]["OLD"] == "remove"


@pytest.mark.parametrize(
    "value",
    [
        {"env_vars": {"BAD-KEY": "secret"}},
        {"env_vars": {"LAMBCHAT_WORKSPACE": "secret"}},
        {"env_vars": {"LAMBCHAT_SHARED": "secret"}},
        {"env_vars": {"X": "secret\x00"}},
        {"env_vars": {"X": "***"}},
        {"env_vars": {"X": "s" * 16001}},
        {"enable_thinking": "extreme"},
        {"sandbox": "remote-shell"},
        {"unexpected": "secret"},
    ],
)
def test_invalid_runtime_settings_fail_without_echoing_secret_values(value):
    with pytest.raises(ValueError) as error:
        normalize_runtime_config(value)
    assert "secret" not in str(error.value)


async def test_options_only_carry_an_owner_scoped_environment_reference():
    config = {
        "channel_type": "telegram",
        "instance_id": "instance",
        "model_id": "m",
        "runtime_config": {
            "sandbox": "local",
            "sandbox_machine_id": "machine",
            "enable_thinking": "high",
            "response_language": "zh",
            "env_vars": {"API_KEY": "secret"},
        },
    }
    result = await build_channel_agent_options(config, "owner")
    assert result == {
        "sandbox": "local",
        "sandbox_machine_id": "machine",
        "enable_thinking": "high",
        "response_language": "zh",
        "model_id": "m",
        "channel_runtime": {"channel_type": "telegram", "instance_id": "instance"},
    }
    assert "secret" not in repr(result)


async def test_project_workspace_is_resolved_for_owner_and_binds_machine(monkeypatch):
    workspace = SimpleNamespace(
        model_dump=lambda **kw: {
            "id": "local-" + "a" * 32,
            "machineId": "project-machine",
            "path": "/repo",
        }
    )
    get = AsyncMock(return_value=SimpleNamespace(workspace=workspace))
    monkeypatch.setattr("src.infra.folder.storage.ProjectStorage.get_by_id", get)
    result = await build_channel_agent_options(
        {"project_id": "p", "runtime_config": {"sandbox": "cloud"}}, "owner"
    )
    get.assert_awaited_once_with("p", "owner")
    assert result["sandbox"] == "local"
    assert result["sandbox_machine_id"] == "project-machine"
    assert "local-" in result["sandbox_workspace"]


async def test_deleted_or_foreign_project_does_not_run_in_a_different_directory(monkeypatch):
    monkeypatch.setattr(
        "src.infra.folder.storage.ProjectStorage.get_by_id", AsyncMock(return_value=None)
    )
    with pytest.raises(ValueError):
        await build_channel_agent_options({"project_id": "foreign"}, "owner")
