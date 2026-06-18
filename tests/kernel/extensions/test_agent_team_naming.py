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


def test_legacy_team_id_chat_field_stays_scoped_to_legacy_team_agent() -> None:
    source = Path("src/api/routes/chat.py").read_text(encoding="utf-8")

    assert (
        f'if agent_id == "{AGENT_TEAM_NAMING.legacy_agent_id}" '
        f"and request.{AGENT_TEAM_NAMING.legacy_chat_field}:"
    ) in source


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
