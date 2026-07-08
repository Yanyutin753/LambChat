from pathlib import Path

from src.api.routes.registry import CORE_ROUTE_REGISTRATIONS
from src.kernel.extensions import (
    AGENT_TEAM_NAMING,
    AGENT_TEAM_PLUGIN_ID,
    BUILTIN_PLUGIN_MANIFESTS,
    USER_AGENT_NAMING,
    ExtensionManifest,
    ExtensionType,
    PluginManifest,
)
from src.kernel.extensions.plugin_options import AGENT_TEAM_SELECTED_TEAM_OPTION
from src.kernel.schemas.agent import AgentRequest, UserAgentPreference
from src.kernel.types import Permission


def _core_route_prefix(route_id: str) -> str:
    return next(
        registration.prefix
        for registration in CORE_ROUTE_REGISTRATIONS
        if registration.id == route_id
    )


def _agent_team_plugin_route_prefix() -> str:
    manifest = next(plugin for plugin in BUILTIN_PLUGIN_MANIFESTS if plugin.id == AGENT_TEAM_PLUGIN_ID)
    return next(route.prefix for route in manifest.routers if route.name == "agent_team-api")


def test_agent_team_naming_keeps_legacy_external_contracts() -> None:
    assert AGENT_TEAM_NAMING.legacy_agent_id == "team"
    assert AGENT_TEAM_NAMING.legacy_api_prefix == "/api/teams"
    assert _agent_team_plugin_route_prefix() == AGENT_TEAM_NAMING.legacy_api_prefix
    assert all(registration.id != "teams" for registration in CORE_ROUTE_REGISTRATIONS)

    assert AGENT_TEAM_NAMING.legacy_permission_prefix == "team"
    assert AGENT_TEAM_NAMING.legacy_permissions == (
        Permission.TEAM_READ.value,
        Permission.TEAM_WRITE.value,
        Permission.TEAM_DELETE.value,
    )
    assert all(
        permission.startswith(f"{AGENT_TEAM_NAMING.legacy_permission_prefix}:")
        for permission in AGENT_TEAM_NAMING.legacy_permissions
    )

    assert AGENT_TEAM_NAMING.legacy_chat_field == "team_id"
    assert AGENT_TEAM_NAMING.legacy_chat_field in AgentRequest.model_fields


def test_agent_team_manifest_uses_agent_team_name_without_renaming_legacy_api() -> None:
    manifest = ExtensionManifest(
        id=AGENT_TEAM_NAMING.manifest_id,
        type=AGENT_TEAM_NAMING.extension_type,
        name="Agent Team",
        version="1.0.0",
        publisher="LambChat",
        capabilities=[AGENT_TEAM_NAMING.extension_type],
        permissions=list(AGENT_TEAM_NAMING.legacy_permissions),
    )
    plugin = PluginManifest(
        id=AGENT_TEAM_NAMING.manifest_id,
        name="Agent Team",
        version="1.0.0",
        api_version="v1",
        permissions=[Permission.TEAM_READ.value],
        frontend={"nav_items": [AGENT_TEAM_NAMING.extension_type]},
    )

    assert manifest.type is ExtensionType.AGENT_TEAM
    assert manifest.capabilities == ["agent_team"]
    assert manifest.type.value != AGENT_TEAM_NAMING.legacy_permission_prefix
    assert plugin.frontend.nav_items == ["agent_team"]
    assert _agent_team_plugin_route_prefix() == "/api/teams"


def test_agent_team_page_uses_agent_team_route_identity() -> None:
    manifest = next(plugin for plugin in BUILTIN_PLUGIN_MANIFESTS if plugin.id == AGENT_TEAM_PLUGIN_ID)

    assert manifest.frontend.app_tabs[0].id == "agent_team:agent-team-tab"
    assert manifest.frontend.app_tabs[0].tab == "agent-team"
    assert manifest.frontend.app_tabs[0].path == "/agent-team"
    assert manifest.frontend.app_tabs[0].panel == "agent_team:agent-team-panel"
    assert manifest.frontend.app_panels[0].id == "agent_team:agent-team-panel"
    assert manifest.frontend.app_panels[0].tab == "agent-team"
    assert manifest.frontend.sidebar_items[0].id == "agent_team:agent-team-nav"
    assert manifest.frontend.sidebar_items[0].path == "/agent-team"


def test_agent_team_manifest_declares_legacy_team_agent_entry() -> None:
    manifest = next(plugin for plugin in BUILTIN_PLUGIN_MANIFESTS if plugin.id == AGENT_TEAM_PLUGIN_ID)

    assert [agent.id for agent in manifest.agents] == ["team"]
    assert manifest.agents[0].module == "src.agents.team_agent.graph.TeamAgent"
    assert manifest.agents[0].required_permissions == [Permission.TEAM_READ.value]


def test_agent_team_declares_chat_input_and_mention_contributions() -> None:
    manifest = next(plugin for plugin in BUILTIN_PLUGIN_MANIFESTS if plugin.id == AGENT_TEAM_PLUGIN_ID)

    assert [option.id for option in manifest.frontend.chat_input_options] == [
        "agent_team:select-team"
    ]
    assert manifest.frontend.chat_input_options[0].panel == "agent_team:team-picker"
    assert manifest.frontend.chat_input_options[0].selected_renderer == "agent_team.SelectedTeamChip"
    assert manifest.frontend.chat_input_options[0].suppresses_core_persona_selector is True
    assert manifest.frontend.chat_input_options[0].shortcut == "mod+t"
    assert manifest.frontend.chat_input_options[0].visible_when is not None
    assert manifest.frontend.chat_input_options[0].visible_when.agent_id == "team"
    assert [panel.id for panel in manifest.frontend.chat_input_panels] == [
        "agent_team:team-picker"
    ]
    assert manifest.frontend.chat_input_panels[0].renderer == "agent_team.TeamPickerModal"
    assert manifest.frontend.chat_input_panels[0].create_path == "/agent-team"
    assert manifest.frontend.chat_input_panels[0].manage_path == "/agent-team"
    assert [provider.id for provider in manifest.frontend.mention_providers] == [
        "agent_team:team-mentions"
    ]
    assert manifest.frontend.mention_providers[0].provider == "agent_team.searchTeams"
    assert manifest.frontend.mention_providers[0].option_binding is not None
    assert manifest.frontend.mention_providers[0].option_binding.plugin_id == AGENT_TEAM_PLUGIN_ID
    assert manifest.frontend.mention_providers[0].option_binding.key == "SELECTED_TEAM_ID"
    assert manifest.frontend.mention_providers[0].option_binding.scope == "session"
    assert [surface.id for surface in manifest.frontend.welcome_surfaces] == [
        "agent_team:team-welcome"
    ]
    assert manifest.frontend.welcome_surfaces[0].agent_id == "team"
    assert manifest.frontend.welcome_surfaces[0].renderer == "agent_team.TeamWelcomeSurface"
    assert manifest.frontend.welcome_surfaces[0].option_binding is not None
    assert manifest.frontend.welcome_surfaces[0].option_binding.plugin_id == AGENT_TEAM_PLUGIN_ID
    assert manifest.frontend.welcome_surfaces[0].option_binding.key == "SELECTED_TEAM_ID"
    assert manifest.frontend.welcome_surfaces[0].option_binding.scope == "session"
    assert manifest.frontend.welcome_surfaces[0].visible_when is not None
    assert manifest.frontend.welcome_surfaces[0].visible_when.agent_id == "team"
    assert [resolver.id for resolver in manifest.frontend.assistant_identity_resolvers] == [
        "agent_team:team-assistant-identity"
    ]
    assert manifest.frontend.assistant_identity_resolvers[0].resolver == "agent_team.TeamAssistantIdentity"
    assert manifest.frontend.assistant_identity_resolvers[0].option_binding is not None
    assert manifest.frontend.assistant_identity_resolvers[0].option_binding.plugin_id == AGENT_TEAM_PLUGIN_ID
    assert manifest.frontend.assistant_identity_resolvers[0].option_binding.key == "SELECTED_TEAM_ID"
    assert manifest.frontend.assistant_identity_resolvers[0].option_binding.scope == "session"
    assert [option.key for option in manifest.frontend.project_options] == [
        "DEFAULT_TEAM_ID"
    ]
    assert manifest.frontend.project_options[0].label == "agentTeam.settings.defaultTeam"
    assert manifest.frontend.project_options[0].renderer == "agent_team.TeamSelectOption"
    assert [option.key for option in manifest.frontend.session_options] == [
        "SELECTED_TEAM_ID"
    ]
    assert manifest.frontend.session_options[0].visible_when is not None
    assert manifest.frontend.session_options[0].visible_when.agent_id == "team"
    assert [option.key for option in manifest.frontend.channel_options] == [
        "SELECTED_TEAM_ID"
    ]
    assert manifest.frontend.channel_options[0].label == "agentTeam.channel.selectedTeam"
    assert manifest.frontend.channel_options[0].renderer == "agent_team.TeamSelectOption"
    assert manifest.frontend.channel_options[0].suppresses_core_persona_selector is True
    assert manifest.frontend.channel_options[0].legacy_payload_keys == ["team_id"]
    assert manifest.frontend.channel_options[0].visible_when is not None
    assert manifest.frontend.channel_options[0].visible_when.route == "/channels/feishu"
    assert [option.key for option in manifest.frontend.scheduled_task_options] == [
        "SELECTED_TEAM_ID"
    ]
    assert manifest.frontend.scheduled_task_options[0].renderer == "agent_team.TeamSelectOption"
    assert manifest.frontend.scheduled_task_options[0].suppresses_core_persona_selector is True
    assert manifest.frontend.scheduled_task_options[0].legacy_payload_keys == ["team_id"]
    assert manifest.frontend.scheduled_task_options[0].visible_when is not None
    assert manifest.frontend.scheduled_task_options[0].visible_when.agent_id == "team"


def test_legacy_team_id_chat_field_stays_scoped_to_legacy_team_agent() -> None:
    source = Path("src/api/routes/chat.py").read_text(encoding="utf-8")

    assert "agent_uses_agent_team_options(agent_id" in source
    assert f"request.{AGENT_TEAM_NAMING.legacy_chat_field}" in source
    assert "apply_declared_plugin_session_options" in source
    assert "apply_agent_team_plugin_session_option" in source
    assert "key=AGENT_TEAM_SELECTED_TEAM_OPTION" in source
    assert AGENT_TEAM_SELECTED_TEAM_OPTION == "SELECTED_TEAM_ID"


def test_user_agent_reserved_name_is_independent_from_agent_team_model() -> None:
    user_agent_manifest = ExtensionManifest(
        id="user-agent",
        type=USER_AGENT_NAMING.extension_type,
        name="User Agent",
        version="1.0.0",
        publisher="LambChat",
        capabilities=[USER_AGENT_NAMING.extension_type],
    )

    assert user_agent_manifest.type is ExtensionType.USER_AGENT
    assert USER_AGENT_NAMING.extension_type == "user_agent"
    assert USER_AGENT_NAMING.extension_type != AGENT_TEAM_NAMING.extension_type
    assert USER_AGENT_NAMING.reuses_agent_team_model is False
    assert {"team_id", "members", "role_name"}.issubset(
        set(USER_AGENT_NAMING.forbidden_agent_team_fields)
    )
    assert set(UserAgentPreference.model_fields).isdisjoint(
        USER_AGENT_NAMING.forbidden_agent_team_fields
    )
