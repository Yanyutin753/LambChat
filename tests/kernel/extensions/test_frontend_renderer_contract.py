from __future__ import annotations

import re
from pathlib import Path

from src.kernel.extensions import PluginPackageScanner
from src.kernel.extensions.host_slots import CONTROLLED_FRONTEND_REFERENCES

REPO_ROOT = Path(__file__).resolve().parents[3]


REGISTRY_SOURCES = {
    "app_panels.renderer": "frontend/src/components/layout/AppContent/TabContent.tsx",
    "message_actions.renderer": "frontend/src/components/chat/ChatMessage/messageActionRenderers.tsx",
    "chat_input_options.selected_renderer": "frontend/src/components/chat/chatInputSelectedRenderers.tsx",
    "chat_input_panels.renderer": "frontend/src/components/chat/chatInputPanelRenderers.tsx",
    "mention_providers.provider": "frontend/src/components/chat/chatMentionProviderRenderers.tsx",
    "welcome_surfaces.renderer": "frontend/src/components/chat/welcomeSurfaceRenderers.tsx",
    "assistant_identity_resolvers.resolver": "frontend/src/components/chat/chatAssistantIdentityResolvers.ts",
    "project_options.renderer": "frontend/src/components/sidebar/projectOptionRenderers.tsx",
    "session_options.renderer": "frontend/src/components/sidebar/projectOptionRenderers.tsx",
    "channel_options.renderer": "frontend/src/components/panels/channel/ChannelPluginOptions.tsx",
    "channel_connectors.panel_renderer": "frontend/src/components/pages/channelConnectorPanelRenderers.tsx",
    "scheduled_task_options.renderer": "frontend/src/components/panels/ScheduledTaskPanel/scheduledTaskOptionRenderers.tsx",
}

PLUGIN_REFERENCE_RE = re.compile(
    r"[\"']((?:agent_team|workflow|feedback|usage_reports|feishu_connector)\.[A-Za-z0-9_]+)[\"']"
)


def _source(path_from_root: str) -> str:
    return (REPO_ROOT / path_from_root).read_text(encoding="utf-8")


def _string_literal_exists(source: str, value: str) -> bool:
    # The frontend registries use ordinary string literal object keys. Match
    # either quote style so future formatting changes do not weaken the contract.
    return re.search(rf"[\"']{re.escape(value)}[\"']", source) is not None


def test_controlled_frontend_references_are_registered_in_frontend_sources() -> None:
    missing: list[tuple[str, str, str]] = []
    for contract_key, references in CONTROLLED_FRONTEND_REFERENCES.items():
        source_path = REGISTRY_SOURCES[contract_key]
        source = _source(source_path)
        for reference in references:
            if not _string_literal_exists(source, reference):
                missing.append((contract_key, reference, source_path))

    assert missing == []


def test_frontend_registered_plugin_references_are_declared_in_kernel_contract() -> None:
    allowed_by_source: dict[str, set[str]] = {}
    for contract_key, source_path in REGISTRY_SOURCES.items():
        allowed_by_source.setdefault(source_path, set()).update(
            CONTROLLED_FRONTEND_REFERENCES[contract_key]
        )

    extra: list[tuple[str, str]] = []
    for source_path, allowed in allowed_by_source.items():
        source = _source(source_path)
        registered = set(PLUGIN_REFERENCE_RE.findall(source))
        for reference in sorted(registered - allowed):
            extra.append((source_path, reference))

    assert extra == []


def test_frontend_renderer_contract_tracks_every_controlled_reference_area() -> None:
    assert set(REGISTRY_SOURCES) == set(CONTROLLED_FRONTEND_REFERENCES)


def test_builtin_frontend_manifest_references_are_declared_in_kernel_contract() -> None:
    scan = PluginPackageScanner(
        plugin_root=REPO_ROOT / "plugins",
        data_root=REPO_ROOT / "plugin-data",
    ).scan()
    missing: list[tuple[str, str, str]] = []

    assert scan.errors == ()
    for descriptor in scan.descriptors:
        if descriptor.source_type not in {"system", "preinstalled"}:
            continue
        manifest = descriptor.manifest
        assert manifest is not None
        frontend = manifest.frontend
        references = {
            "app_panels.renderer": [item.renderer for item in frontend.app_panels],
            "message_actions.renderer": [item.renderer for item in frontend.message_actions],
            "chat_input_options.selected_renderer": [
                item.selected_renderer for item in frontend.chat_input_options if item.selected_renderer
            ],
            "chat_input_panels.renderer": [item.renderer for item in frontend.chat_input_panels],
            "mention_providers.provider": [item.provider for item in frontend.mention_providers],
            "welcome_surfaces.renderer": [item.renderer for item in frontend.welcome_surfaces],
            "assistant_identity_resolvers.resolver": [
                item.resolver for item in frontend.assistant_identity_resolvers
            ],
            "project_options.renderer": [
                item.renderer for item in frontend.project_options if item.renderer
            ],
            "session_options.renderer": [
                item.renderer for item in frontend.session_options if item.renderer
            ],
            "channel_options.renderer": [
                item.renderer for item in frontend.channel_options if item.renderer
            ],
            "channel_connectors.panel_renderer": [
                item.panel_renderer
                for item in frontend.channel_connectors
                if item.panel_renderer
            ],
            "scheduled_task_options.renderer": [
                item.renderer for item in frontend.scheduled_task_options if item.renderer
            ],
        }
        for contract_key, values in references.items():
            allowed = CONTROLLED_FRONTEND_REFERENCES[contract_key]
            for value in values:
                if value not in allowed:
                    missing.append((descriptor.plugin_id, contract_key, value))

    assert missing == []
