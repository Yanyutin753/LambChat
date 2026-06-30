"""Static built-in plugin manifests and migration assessments."""

from __future__ import annotations

from src.kernel.config import settings
from src.kernel.extensions.manifest import PluginInstallType, PluginManifest
from src.kernel.extensions.plugin_options import AGENT_TEAM_SELECTED_TEAM_OPTION
from src.kernel.types import Permission
from src.plugins.feedback.manifest import build_feedback_plugin_manifest

IMAGE_GENERATION_PLUGIN_ID = "image_generation"
AUDIO_TRANSCRIPTION_PLUGIN_ID = "audio_transcription"
USAGE_REPORTS_PLUGIN_ID = "usage_reports"
ADVANCED_FILE_VIEWERS_PLUGIN_ID = "advanced_file_viewers"
GITHUB_INSTALLER_PLUGIN_ID = "github_installer"
FEISHU_CONNECTOR_PLUGIN_ID = "feishu_connector"
FEISHU_CONNECTOR_ID = "feishu_connector:feishu"
AGENT_TEAM_PLUGIN_ID = "agent_team"
WORKFLOW_PLUGIN_ID = "workflow"


def build_agent_team_plugin_manifest() -> PluginManifest:
    """Return the static manifest for the built-in Agent Team capability."""
    return PluginManifest(
        id=AGENT_TEAM_PLUGIN_ID,
        name="Agent Team",
        version="1.0.0",
        api_version="v1",
        permissions=[
            Permission.TEAM_READ.value,
            Permission.TEAM_WRITE.value,
            Permission.TEAM_DELETE.value,
        ],
        settings=[
            {
                "key": "DEFAULT_TEAM_ID",
                "type": "string",
                "label": "agentTeam.settings.defaultTeam",
                "description": "Default Agent Team selected for this project.",
                "default": "",
                "scope": "project",
                "group": "project",
                "order": 10,
            },
            {
                "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                "type": "string",
                "label": "agentTeam.session.selectedTeam",
                "description": "Agent Team selected for the current chat session.",
                "default": "",
                "scope": "session",
                "group": "session",
                "order": 10,
            },
            {
                "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                "type": "string",
                "label": "agentTeam.channel.selectedTeam",
                "description": "Agent Team selected for plugin-owned channel runs.",
                "default": "",
                "scope": "channel",
                "group": "channel",
                "order": 10,
            },
            {
                "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                "type": "string",
                "label": "agentTeam.scheduledTask.selectedTeam",
                "description": "Agent Team selected for plugin-owned scheduled task runs.",
                "default": "",
                "scope": "scheduled_task",
                "group": "scheduled_task",
                "order": 10,
            },
        ],
        routers=[
            {
                "name": "agent_team-api",
                "prefix": "/api/teams",
                "module": "src.api.routes.team",
                "required_permissions": [
                    Permission.TEAM_READ.value,
                    Permission.TEAM_WRITE.value,
                    Permission.TEAM_DELETE.value,
                ],
                "tags": ["Teams"],
            }
        ],
        agents=[
            {
                "id": "team",
                "module": "src.agents.team_agent.graph.TeamAgent",
                "name": "agents.team.name",
                "description": "agents.team.description",
                "icon": "Users",
                "sort_order": 15,
                "category": "agent_team:team-builder",
                "required_permissions": [Permission.TEAM_READ.value],
            }
        ],
        tools=[
            {
                "name": "search_persona_presets",
                "module": "src.infra.tool.team_tool",
                "required_permissions": [
                    Permission.TEAM_READ.value,
                    Permission.PERSONA_PRESET_READ.value,
                    Permission.CHAT_WRITE.value,
                ],
                "legacy_ids": ["search_persona_presets", "agent_team.search_persona_presets"],
            },
            {
                "name": "create_agent_team",
                "module": "src.infra.tool.team_tool",
                "required_permissions": [
                    Permission.TEAM_WRITE.value,
                    Permission.CHAT_WRITE.value,
                ],
                "legacy_ids": ["create_agent_team", "agent_team.create_agent_team"],
            },
        ],
        frontend={
            "app_tabs": [
                {
                    "id": "agent_team:agent-team-tab",
                    "tab": "agent-team",
                    "path": "/agent-team",
                    "label": "nav.team",
                    "panel": "agent_team:agent-team-panel",
                    "insert_after": "agents",
                    "order": 420,
                    "permissions": [Permission.TEAM_READ.value],
                    "seo_title": "seo.team.title",
                    "seo_description": "seo.team.description",
                }
            ],
            "app_panels": [
                {
                    "id": "agent_team:agent-team-panel",
                    "tab": "agent-team",
                    "renderer": "agent_team.TeamBuilderPanel",
                }
            ],
            "sidebar_items": [
                {
                    "id": "agent_team:agent-team-nav",
                    "path": "/agent-team",
                    "label": "nav.team",
                    "icon": "Users",
                    "order": 20,
                    "permissions": [Permission.TEAM_READ.value],
                }
            ],
            "tool_renderers": ["agent_team:agent-team"],
            "chat_input_options": [
                {
                    "id": "agent_team:select-team",
                    "slot": "enhance",
                    "label": "featureMenu.team",
                    "icon": "UsersRound",
                    "panel": "agent_team:team-picker",
                    "selected_renderer": "agent_team.SelectedTeamChip",
                    "suppresses_core_persona_selector": True,
                    "shortcut": "mod+t",
                    "order": 20,
                    "option_binding": {
                        "plugin_id": "agent_team",
                        "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                        "scope": "session",
                    },
                    "visible_when": {"agent_id": "team"},
                }
            ],
            "chat_input_panels": [
                {
                    "id": "agent_team:team-picker",
                    "renderer": "agent_team.TeamPickerModal",
                    "create_path": "/agent-team",
                    "manage_path": "/agent-team",
                    "option_binding": {
                        "plugin_id": "agent_team",
                        "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                        "scope": "session",
                    },
                    "visible_when": {"agent_id": "team"},
                }
            ],
            "mention_providers": [
                {
                    "id": "agent_team:team-mentions",
                    "trigger": "@",
                    "mode": "team",
                    "provider": "agent_team.searchTeams",
                    "option_binding": {
                        "plugin_id": AGENT_TEAM_PLUGIN_ID,
                        "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                        "scope": "session",
                    },
                    "visible_when": {"agent_id": "team"},
                }
            ],
            "welcome_surfaces": [
                {
                    "id": "agent_team:team-welcome",
                    "agent_id": "team",
                    "renderer": "agent_team.TeamWelcomeSurface",
                    "order": 20,
                    "option_binding": {
                        "plugin_id": AGENT_TEAM_PLUGIN_ID,
                        "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                        "scope": "session",
                    },
                    "visible_when": {"agent_id": "team"},
                }
            ],
            "assistant_identity_resolvers": [
                {
                    "id": "agent_team:team-assistant-identity",
                    "agent_id": "team",
                    "resolver": "agent_team.TeamAssistantIdentity",
                    "order": 20,
                    "option_binding": {
                        "plugin_id": AGENT_TEAM_PLUGIN_ID,
                        "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                        "scope": "session",
                    },
                    "visible_when": {"agent_id": "team"},
                }
            ],
            "agent_categories": [
                {
                    "id": "agent_team:team-builder",
                    "label": "agentTeam.category.teamBuilder",
                    "description": "Agent Team owned team-building agents.",
                    "icon": "Users",
                    "order": 20,
                }
            ],
            "project_options": [
                {
                    "key": "DEFAULT_TEAM_ID",
                    "type": "string",
                    "label": "agentTeam.settings.defaultTeam",
                    "description": "Default Agent Team selected for this project.",
                    "group": "project",
                    "order": 10,
                    "renderer": "agent_team.TeamSelectOption",
                    "applies_to_session_key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                }
            ],
            "session_options": [
                {
                    "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                    "type": "string",
                    "label": "agentTeam.session.selectedTeam",
                    "description": "Agent Team selected for the current chat session.",
                    "group": "session",
                    "order": 10,
                    "suppresses_core_persona_selector": True,
                    "legacy_payload_keys": ["team_id"],
                    "visible_when": {"agent_id": "team"},
                }
            ],
            "channel_options": [
                {
                    "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                    "type": "string",
                    "label": "agentTeam.channel.selectedTeam",
                    "description": "Agent Team selected for plugin-owned channel runs.",
                    "group": "channel",
                    "order": 10,
                    "renderer": "agent_team.TeamSelectOption",
                    "suppresses_core_persona_selector": True,
                    "legacy_payload_keys": ["team_id"],
                    "visible_when": {"route": "/channels/feishu"},
                }
            ],
            "scheduled_task_options": [
                {
                    "key": AGENT_TEAM_SELECTED_TEAM_OPTION,
                    "type": "string",
                    "label": "agentTeam.scheduledTask.selectedTeam",
                    "description": "Agent Team selected for plugin-owned scheduled task runs.",
                    "group": "scheduled_task",
                    "order": 10,
                    "renderer": "agent_team.TeamSelectOption",
                    "suppresses_core_persona_selector": True,
                    "legacy_payload_keys": ["team_id"],
                    "visible_when": {"agent_id": "team"},
                }
            ],
            "i18n_namespaces": ["agent_team:team"],
            "required_permissions": [Permission.TEAM_READ.value],
        },
        resources=[
            {
                "id": "teams",
                "type": "db_collection",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "mongodb",
                    "manager": "src.infra.team.manager.TeamManager",
                    "schema": "src.kernel.schemas.team.TeamResponse",
                    "data_policy": "Disable/uninstall dry-run keeps user team definitions.",
                },
            },
            {
                "id": "teams.owner_updated_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "teams",
                    "fields": "owner_user_id,updated_at:-1",
                },
            },
            {
                "id": "teams.owner_name_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {"collection": "teams", "fields": "owner_user_id,name"},
            },
            {
                "id": "users.metadata.pinned_team_ids",
                "type": "db_document",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "collection": "users",
                    "field": "metadata.pinned_team_ids",
                    "reason": "Pinned Team preferences must survive AgentTeam disable/uninstall.",
                },
            },
            {
                "id": "users.metadata.favorite_team_ids",
                "type": "db_document",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "collection": "users",
                    "field": "metadata.favorite_team_ids",
                    "reason": "Favorite Team preferences must survive AgentTeam disable/uninstall.",
                },
            },
        ],
        enabled_by_default=True,
        core=False,
        install_type=PluginInstallType.SYSTEM_BUILTIN,
    )


def build_workflow_plugin_manifest() -> PluginManifest:
    """Return the static manifest for the workflow plugin shell."""
    return PluginManifest(
        id=WORKFLOW_PLUGIN_ID,
        name="workflowPlugin.plugin.name",
        description="workflowPlugin.plugin.description",
        version="0.1.0",
        api_version="v1",
        permissions=[
            Permission.WORKFLOW_READ.value,
            Permission.WORKFLOW_WRITE.value,
            Permission.WORKFLOW_RUN.value,
            Permission.WORKFLOW_ADMIN.value,
            Permission.WORKFLOW_PUBLISH.value,
            Permission.WORKFLOW_CREDENTIAL_MANAGE.value,
        ],
        settings=[
            {
                "key": "DEFAULT_MODEL",
                "type": "string",
                "label": "pluginSettings.workflow.DEFAULT_MODEL.label",
                "description": "pluginSettings.workflow.DEFAULT_MODEL.description",
                "default": "",
                "scope": "system",
                "group": "runtime",
                "order": 10,
            },
            {
                "key": "DEFAULT_TIMEOUT_SECONDS",
                "type": "number",
                "label": "pluginSettings.workflow.DEFAULT_TIMEOUT_SECONDS.label",
                "description": "pluginSettings.workflow.DEFAULT_TIMEOUT_SECONDS.description",
                "default": 120,
                "scope": "system",
                "group": "runtime",
                "order": 20,
            },
            {
                "key": "MAX_NODES_PER_WORKFLOW",
                "type": "number",
                "label": "pluginSettings.workflow.MAX_NODES_PER_WORKFLOW.label",
                "description": "pluginSettings.workflow.MAX_NODES_PER_WORKFLOW.description",
                "default": 100,
                "scope": "system",
                "group": "limits",
                "order": 30,
            },
            {
                "key": "MAX_RUN_SECONDS",
                "type": "number",
                "label": "pluginSettings.workflow.MAX_RUN_SECONDS.label",
                "description": "pluginSettings.workflow.MAX_RUN_SECONDS.description",
                "default": 300,
                "scope": "system",
                "group": "limits",
                "order": 40,
            },
            {
                "key": "HTTP_NODE_POLICY",
                "type": "string",
                "label": "pluginSettings.workflow.HTTP_NODE_POLICY.label",
                "description": "pluginSettings.workflow.HTTP_NODE_POLICY.description",
                "default": "disabled",
                "scope": "system",
                "group": "security",
                "order": 50,
            },
            {
                "key": "HTTP_ALLOWLIST",
                "type": "json",
                "label": "pluginSettings.workflow.HTTP_ALLOWLIST.label",
                "description": "pluginSettings.workflow.HTTP_ALLOWLIST.description",
                "default": [],
                "scope": "system",
                "group": "security",
                "order": 60,
            },
            {
                "key": "CODE_NODE_POLICY",
                "type": "string",
                "label": "pluginSettings.workflow.CODE_NODE_POLICY.label",
                "description": "pluginSettings.workflow.CODE_NODE_POLICY.description",
                "default": "disabled",
                "scope": "system",
                "group": "security",
                "order": 70,
            },
            {
                "key": "KNOWLEDGE_DATASET_MAPPINGS",
                "type": "json",
                "label": "pluginSettings.workflow.KNOWLEDGE_DATASET_MAPPINGS.label",
                "description": "pluginSettings.workflow.KNOWLEDGE_DATASET_MAPPINGS.description",
                "default": {},
                "scope": "system",
                "group": "runtime",
                "order": 75,
            },
            {
                "key": "CREDENTIAL_REF_MAPPINGS",
                "type": "json",
                "label": "pluginSettings.workflow.CREDENTIAL_REF_MAPPINGS.label",
                "description": "pluginSettings.workflow.CREDENTIAL_REF_MAPPINGS.description",
                "default": {},
                "scope": "system",
                "group": "runtime",
                "order": 76,
                "json_schema": {
                    "type": "object",
                    "additionalProperties": {
                        "type": ["string", "object"],
                        "properties": {
                            "type": {"type": "string"},
                            "target": {"type": "string"},
                            "target_ref": {"type": "string"},
                            "credential_ref": {"type": "string"},
                            "credential_id": {"type": "string"},
                            "model_id": {"type": "string"},
                            "label": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
                    },
                },
            },
            {
                "key": "MAX_EVENT_PAYLOAD_BYTES",
                "type": "number",
                "label": "pluginSettings.workflow.MAX_EVENT_PAYLOAD_BYTES.label",
                "description": "pluginSettings.workflow.MAX_EVENT_PAYLOAD_BYTES.description",
                "default": 65536,
                "scope": "system",
                "group": "limits",
                "order": 80,
            },
            {
                "key": "RUN_LOG_RETENTION_DAYS",
                "type": "number",
                "label": "pluginSettings.workflow.RUN_LOG_RETENTION_DAYS.label",
                "description": "pluginSettings.workflow.RUN_LOG_RETENTION_DAYS.description",
                "default": 30,
                "scope": "system",
                "group": "retention",
                "order": 90,
            },
            {
                "key": "DEFAULT_WORKFLOW_ID",
                "type": "string",
                "label": "workflowPlugin.project.defaultWorkflow",
                "description": "workflowPlugin.project.defaultWorkflowDescription",
                "default": "",
                "scope": "project",
                "group": "workflow",
                "order": 10,
            },
            {
                "key": "DEFAULT_WORKFLOW_VERSION_ID",
                "type": "string",
                "label": "workflowPlugin.project.defaultWorkflowVersion",
                "description": "workflowPlugin.project.defaultWorkflowVersionDescription",
                "default": "",
                "scope": "project",
                "group": "workflow",
                "order": 11,
            },
            {
                "key": "SELECTED_WORKFLOW_ID",
                "type": "string",
                "label": "workflowPlugin.session.selectedWorkflow",
                "description": "workflowPlugin.session.selectedWorkflowDescription",
                "default": "",
                "scope": "session",
                "group": "workflow",
                "order": 10,
            },
            {
                "key": "SELECTED_WORKFLOW_VERSION_ID",
                "type": "string",
                "label": "workflowPlugin.session.selectedWorkflowVersion",
                "description": "workflowPlugin.session.selectedWorkflowVersionDescription",
                "default": "",
                "scope": "session",
                "group": "workflow",
                "order": 11,
            },
            {
                "key": "SELECTED_WORKFLOW_INPUT_JSON",
                "type": "json",
                "label": "workflowPlugin.session.selectedWorkflowInput",
                "description": "workflowPlugin.session.selectedWorkflowInputDescription",
                "default": {},
                "scope": "session",
                "group": "workflow",
                "order": 12,
            },
            {
                "key": "WORKFLOW_ID",
                "type": "string",
                "label": "workflowPlugin.scheduledTask.workflow",
                "description": "workflowPlugin.scheduledTask.workflowDescription",
                "default": "",
                "scope": "scheduled_task",
                "group": "workflow",
                "order": 10,
            },
            {
                "key": "WORKFLOW_VERSION_ID",
                "type": "string",
                "label": "workflowPlugin.scheduledTask.workflowVersion",
                "description": "workflowPlugin.scheduledTask.workflowVersionDescription",
                "default": "",
                "scope": "scheduled_task",
                "group": "workflow",
                "order": 11,
            },
            {
                "key": "WORKFLOW_INPUT_JSON",
                "type": "json",
                "label": "workflowPlugin.scheduledTask.workflowInput",
                "description": "workflowPlugin.scheduledTask.workflowInputDescription",
                "default": {},
                "scope": "scheduled_task",
                "group": "workflow",
                "order": 12,
            },
        ],
        routers=[
            {
                "name": "workflow-api",
                "prefix": "/api/plugins/workflow",
                "module": "src.plugins.workflow.routes",
                "required_permissions": [
                    Permission.WORKFLOW_READ.value,
                    Permission.WORKFLOW_WRITE.value,
                    Permission.WORKFLOW_RUN.value,
                ],
                "tags": ["workflowPlugin.nav.label"],
            }
        ],
        tools=[
            {
                "name": "workflow_run",
                "module": "src.plugins.workflow.tools",
                "required_permissions": [Permission.WORKFLOW_RUN.value],
                "legacy_ids": ["workflow_run"],
            },
            {
                "name": "workflow_list",
                "module": "src.plugins.workflow.tools",
                "required_permissions": [Permission.WORKFLOW_READ.value],
                "legacy_ids": ["workflow_list"],
            },
            {
                "name": "workflow_get_schema",
                "module": "src.plugins.workflow.tools",
                "required_permissions": [Permission.WORKFLOW_READ.value],
                "legacy_ids": ["workflow_get_schema"],
            },
            {
                "name": "workflow_get_run",
                "module": "src.plugins.workflow.tools",
                "required_permissions": [Permission.WORKFLOW_READ.value],
                "legacy_ids": ["workflow_get_run"],
            },
            {
                "name": "workflow_resume",
                "module": "src.plugins.workflow.tools",
                "required_permissions": [Permission.WORKFLOW_RUN.value],
                "legacy_ids": ["workflow_resume"],
            },
        ],
        lifespan_hooks=[
            {
                "name": "workflow:startup",
                "module": "src.plugins.workflow.lifecycle:startup",
                "phase": "startup",
                "order": 50,
            },
            {
                "name": "workflow:shutdown",
                "module": "src.plugins.workflow.lifecycle:shutdown",
                "phase": "shutdown",
                "order": 50,
            },
        ],
        frontend={
            "app_tabs": [
                {
                    "id": "workflow:workflows-tab",
                    "tab": "workflows",
                    "path": "/workflows",
                    "label": "workflowPlugin.nav.label",
                    "panel": "workflow:workflows-panel",
                    "insert_after": "agent-team",
                    "order": 700,
                    "permissions": [Permission.WORKFLOW_READ.value],
                    "seo_title": "seo.workflows.title",
                    "seo_description": "seo.workflows.description",
                    "redirect_to": "/chat",
                    "show_no_permission_toast": True,
                },
                {
                    "id": "workflow:workflow-editor-tab",
                    "tab": "workflows-editor",
                    "path": "/workflows/:workflowId/editor",
                    "label": "workflowPlugin.nav.editorLabel",
                    "panel": "workflow:workflow-editor-panel",
                    "insert_after": "workflows",
                    "order": 701,
                    "permissions": [Permission.WORKFLOW_READ.value],
                    "seo_title": "seo.workflows.editorTitle",
                    "seo_description": "seo.workflows.editorDescription",
                    "redirect_to": "/chat",
                    "show_no_permission_toast": True,
                },
                {
                    "id": "workflow:workflow-run-tab",
                    "tab": "workflows-run",
                    "path": "/workflows/:workflowId/runs/:runId",
                    "label": "workflowPlugin.nav.runLabel",
                    "panel": "workflow:workflow-run-panel",
                    "insert_after": "workflows-editor",
                    "order": 702,
                    "permissions": [Permission.WORKFLOW_READ.value],
                    "seo_title": "seo.workflows.runTitle",
                    "seo_description": "seo.workflows.runDescription",
                    "redirect_to": "/chat",
                    "show_no_permission_toast": True,
                },
            ],
            "app_panels": [
                {
                    "id": "workflow:workflows-panel",
                    "tab": "workflows",
                    "renderer": "workflow.WorkflowPanel",
                },
                {
                    "id": "workflow:workflow-editor-panel",
                    "tab": "workflows-editor",
                    "renderer": "workflow.WorkflowPanel",
                },
                {
                    "id": "workflow:workflow-run-panel",
                    "tab": "workflows-run",
                    "renderer": "workflow.WorkflowPanel",
                },
            ],
            "sidebar_items": [
                {
                    "id": "workflow:workflows-nav",
                    "path": "/workflows",
                    "label": "workflowPlugin.nav.label",
                    "icon": "Workflow",
                    "order": 30,
                    "permissions": [Permission.WORKFLOW_READ.value],
                }
            ],
            "project_options": [
                {
                    "key": "DEFAULT_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflowPlugin.project.defaultWorkflow",
                    "description": "workflowPlugin.project.defaultWorkflowDescription",
                    "group": "workflow",
                    "order": 10,
                    "renderer": "workflow.WorkflowSelectOption",
                    "applies_to_session_key": "SELECTED_WORKFLOW_ID",
                },
                {
                    "key": "DEFAULT_WORKFLOW_VERSION_ID",
                    "type": "string",
                    "label": "workflowPlugin.project.defaultWorkflowVersion",
                    "description": "workflowPlugin.project.defaultWorkflowVersionDescription",
                    "group": "workflow",
                    "order": 11,
                    "renderer": "workflow.WorkflowVersionSelectOption",
                    "applies_to_session_key": "SELECTED_WORKFLOW_VERSION_ID",
                },
            ],
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflowPlugin.session.selectedWorkflow",
                    "description": "workflowPlugin.session.selectedWorkflowDescription",
                    "group": "workflow",
                    "order": 10,
                    "renderer": "workflow.WorkflowSelectOption",
                    "legacy_payload_keys": ["workflow_id"],
                },
                {
                    "key": "SELECTED_WORKFLOW_VERSION_ID",
                    "type": "string",
                    "label": "workflowPlugin.session.selectedWorkflowVersion",
                    "description": "workflowPlugin.session.selectedWorkflowVersionDescription",
                    "group": "workflow",
                    "order": 11,
                    "renderer": "workflow.WorkflowVersionSelectOption",
                    "legacy_payload_keys": ["workflow_version_id", "version_id"],
                },
                {
                    "key": "SELECTED_WORKFLOW_INPUT_JSON",
                    "type": "json",
                    "label": "workflowPlugin.session.selectedWorkflowInput",
                    "description": "workflowPlugin.session.selectedWorkflowInputDescription",
                    "group": "workflow",
                    "order": 12,
                    "renderer": "workflow.WorkflowInputOption",
                    "legacy_payload_keys": ["workflow_input", "input"],
                },
            ],
            "scheduled_task_options": [
                {
                    "key": "WORKFLOW_ID",
                    "type": "string",
                    "label": "workflowPlugin.scheduledTask.workflow",
                    "description": "workflowPlugin.scheduledTask.workflowDescription",
                    "group": "workflow",
                    "order": 10,
                    "renderer": "workflow.WorkflowSelectOption",
                    "legacy_payload_keys": ["workflow_id"],
                },
                {
                    "key": "WORKFLOW_VERSION_ID",
                    "type": "string",
                    "label": "workflowPlugin.scheduledTask.workflowVersion",
                    "description": "workflowPlugin.scheduledTask.workflowVersionDescription",
                    "group": "workflow",
                    "order": 11,
                    "renderer": "workflow.WorkflowVersionSelectOption",
                    "legacy_payload_keys": ["workflow_version_id", "version_id"],
                },
                {
                    "key": "WORKFLOW_INPUT_JSON",
                    "type": "json",
                    "label": "workflowPlugin.scheduledTask.workflowInput",
                    "description": "workflowPlugin.scheduledTask.workflowInputDescription",
                    "group": "workflow",
                    "order": 12,
                    "renderer": "workflow.WorkflowInputOption",
                    "legacy_payload_keys": ["workflow_input", "input"],
                },
            ],
            "chat_input_options": [
                {
                    "id": "workflow:select-workflow",
                    "slot": "enhance",
                    "label": "workflowPlugin.chat.selectWorkflow",
                    "icon": "Workflow",
                    "panel": "workflow:workflow-picker",
                    "selected_renderer": "workflow.SelectedWorkflowChip",
                    "shortcut": "mod+w",
                    "order": 30,
                    "option_binding": {
                        "plugin_id": WORKFLOW_PLUGIN_ID,
                        "key": "SELECTED_WORKFLOW_ID",
                        "scope": "session",
                    },
                }
            ],
            "chat_input_panels": [
                {
                    "id": "workflow:workflow-picker",
                    "renderer": "workflow.WorkflowPickerModal",
                    "create_path": "/workflows?create=blank",
                    "manage_path": "/workflows",
                    "option_binding": {
                        "plugin_id": WORKFLOW_PLUGIN_ID,
                        "key": "SELECTED_WORKFLOW_ID",
                        "scope": "session",
                    },
                }
            ],
            "i18n_namespaces": ["workflow:workflows"],
            "required_permissions": [Permission.WORKFLOW_READ.value],
        },
        resources=[
            {
                "id": "workflow_definitions",
                "type": "db_collection",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "mongodb",
                    "data_policy": "Disable/uninstall keeps workflow definitions.",
                },
            },
            {
                "id": "workflow_versions",
                "type": "db_collection",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "mongodb",
                    "data_policy": "Disable/uninstall keeps workflow versions and source snapshots.",
                },
            },
            {
                "id": "workflow_runs",
                "type": "db_collection",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "mongodb",
                    "data_policy": "Run history is retained by default.",
                },
            },
            {
                "id": "workflow_run_events",
                "type": "db_collection",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "mongodb",
                    "data_policy": "Run trace events are retained by configured retention policy.",
                },
            },
            {
                "id": "workflow_credentials",
                "type": "db_collection",
                "scope": "user",
                "retention_policy": "manual_review_required",
                "cleanup_strategy": "manual_review",
                "metadata": {
                    "storage": "mongodb",
                    "data_policy": "Credential references require manual review on uninstall.",
                },
            },
            {
                "id": "workflow_definitions.workflow_id_unique",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_definitions",
                    "fields": "workflow_id",
                    "unique": "true",
                },
            },
            {
                "id": "workflow_definitions.owner_updated_at_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_definitions",
                    "fields": "owner_user_id,updated_at:-1",
                },
            },
            {
                "id": "workflow_versions.version_id_unique",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_versions",
                    "fields": "version_id",
                    "unique": "true",
                },
            },
            {
                "id": "workflow_versions.workflow_version_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_versions",
                    "fields": "workflow_id,version_number",
                },
            },
            {
                "id": "workflow_runs.run_id_unique",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_runs",
                    "fields": "run_id",
                    "unique": "true",
                },
            },
            {
                "id": "workflow_runs.workflow_started_at_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_runs",
                    "fields": "workflow_id,started_at:-1",
                },
            },
            {
                "id": "workflow_run_events.run_sequence_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_run_events",
                    "fields": "run_id,sequence",
                },
            },
            {
                "id": "workflow_credentials.credential_id_unique",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_credentials",
                    "fields": "credential_id",
                    "unique": "true",
                },
            },
            {
                "id": "workflow_credentials.owner_ref_unique",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_credentials",
                    "fields": "owner_user_id,ref",
                    "unique": "true",
                },
            },
            {
                "id": "workflow_credentials.owner_updated_at_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "workflow_credentials",
                    "fields": "owner_user_id,updated_at:-1",
                },
            },
        ],
        enabled_by_default=False,
        core=False,
        install_type=PluginInstallType.SYSTEM_BUILTIN,
    )


def build_image_generation_plugin_manifest() -> PluginManifest:
    """Return the static manifest for the optional image generation provider."""
    return PluginManifest(
        id=IMAGE_GENERATION_PLUGIN_ID,
        name="Image Generation",
        version="1.0.0",
        api_version="v1",
        permissions=[Permission.MCP_READ.value],
        settings=[
            {
                "key": "API_KEY",
                "type": "string",
                "label": "pluginSettings.image_generation.API_KEY.label",
                "description": "pluginSettings.image_generation.API_KEY.description",
                "default": "",
                "sensitive": True,
                "required": True,
                "group": "provider",
                "order": 10,
                "env_fallback": "IMAGE_GENERATION_API_KEY",
                "legacy_system_setting_keys": ["IMAGE_GENERATION_API_KEY"],
            },
            {
                "key": "BASE_URL",
                "type": "string",
                "label": "pluginSettings.image_generation.BASE_URL.label",
                "description": "pluginSettings.image_generation.BASE_URL.description",
                "default": "https://api.openai.com/v1",
                "group": "provider",
                "order": 20,
                "env_fallback": "IMAGE_GENERATION_BASE_URL",
                "legacy_system_setting_keys": ["IMAGE_GENERATION_BASE_URL"],
            },
            {
                "key": "MODEL",
                "type": "string",
                "label": "pluginSettings.image_generation.MODEL.label",
                "description": "pluginSettings.image_generation.MODEL.description",
                "default": "gpt-image-2",
                "group": "provider",
                "order": 30,
                "env_fallback": "IMAGE_GENERATION_MODEL",
                "legacy_system_setting_keys": ["IMAGE_GENERATION_MODEL"],
            },
            {
                "key": "TIMEOUT",
                "type": "number",
                "label": "pluginSettings.image_generation.TIMEOUT.label",
                "description": "pluginSettings.image_generation.TIMEOUT.description",
                "default": 120,
                "group": "provider",
                "order": 40,
                "env_fallback": "IMAGE_GENERATION_TIMEOUT",
                "legacy_system_setting_keys": ["IMAGE_GENERATION_TIMEOUT"],
            },
        ],
        legacy_system_settings=["ENABLE_IMAGE_GENERATION"],
        tools=[
            {
                "name": "image_generate",
                "module": "src.infra.tool.image_generation_tool",
                "required_permissions": [Permission.MCP_READ.value],
                "legacy_ids": ["image_generate"],
            }
        ],
        frontend={
            "tool_renderers": ["image_generation:image-generate"],
        },
        resources=[
            {
                "id": "IMAGE_GENERATION_API_KEY",
                "type": "env_key_declaration",
                "scope": "system",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "setting": "IMAGE_GENERATION_API_KEY",
                    "secret": "true",
                },
            },
            {
                "id": "generated-images/{user_id}",
                "type": "file",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "s3_or_local",
                    "producer": "src.infra.tool.image_generation_tool.image_generate",
                },
            },
        ],
        enabled_by_default=bool(settings.ENABLE_IMAGE_GENERATION),
        core=False,
        install_type=PluginInstallType.PREINSTALLED,
    )


def build_audio_transcription_plugin_manifest() -> PluginManifest:
    """Return the static manifest for the optional audio transcription provider."""
    return PluginManifest(
        id=AUDIO_TRANSCRIPTION_PLUGIN_ID,
        name="Audio Transcription",
        version="1.0.0",
        api_version="v1",
        permissions=[Permission.MCP_READ.value],
        settings=[
            {
                "key": "API_KEY",
                "type": "string",
                "label": "pluginSettings.audio_transcription.API_KEY.label",
                "description": "pluginSettings.audio_transcription.API_KEY.description",
                "default": "",
                "sensitive": True,
                "required": True,
                "group": "provider",
                "order": 10,
                "env_fallback": "AUDIO_TRANSCRIPTION_API_KEY",
                "legacy_system_setting_keys": ["AUDIO_TRANSCRIPTION_API_KEY"],
            },
            {
                "key": "BASE_URL",
                "type": "string",
                "label": "pluginSettings.audio_transcription.BASE_URL.label",
                "description": "pluginSettings.audio_transcription.BASE_URL.description",
                "default": "",
                "group": "provider",
                "order": 20,
                "env_fallback": "AUDIO_TRANSCRIPTION_BASE_URL",
                "legacy_system_setting_keys": ["AUDIO_TRANSCRIPTION_BASE_URL"],
            },
            {
                "key": "MODEL",
                "type": "string",
                "label": "pluginSettings.audio_transcription.MODEL.label",
                "description": "pluginSettings.audio_transcription.MODEL.description",
                "default": "gpt-4o-mini-transcribe",
                "group": "provider",
                "order": 30,
                "env_fallback": "AUDIO_TRANSCRIPTION_MODEL",
                "legacy_system_setting_keys": ["AUDIO_TRANSCRIPTION_MODEL"],
            },
            {
                "key": "MAX_DOWNLOAD_BYTES",
                "type": "number",
                "label": "pluginSettings.audio_transcription.MAX_DOWNLOAD_BYTES.label",
                "description": "pluginSettings.audio_transcription.MAX_DOWNLOAD_BYTES.description",
                "default": 52428800,
                "group": "limits",
                "order": 40,
                "env_fallback": "AUDIO_TRANSCRIPTION_MAX_DOWNLOAD_BYTES",
                "legacy_system_setting_keys": ["AUDIO_TRANSCRIPTION_MAX_DOWNLOAD_BYTES"],
            },
        ],
        legacy_system_settings=["ENABLE_AUDIO_TRANSCRIPTION"],
        tools=[
            {
                "name": "audio_transcribe",
                "module": "src.infra.tool.audio_transcribe_tool",
                "required_permissions": [Permission.MCP_READ.value],
                "legacy_ids": ["audio_transcribe"],
            }
        ],
        frontend={
            "tool_renderers": ["audio_transcription:audio-transcribe"],
        },
        resources=[
            {
                "id": "AUDIO_TRANSCRIPTION_API_KEY",
                "type": "env_key_declaration",
                "scope": "system",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "setting": "AUDIO_TRANSCRIPTION_API_KEY",
                    "secret": "true",
                },
            }
        ],
        enabled_by_default=bool(settings.ENABLE_AUDIO_TRANSCRIPTION),
        core=False,
        install_type=PluginInstallType.PREINSTALLED,
    )


def build_usage_reports_plugin_manifest() -> PluginManifest:
    """Return the static manifest for the usage reporting read surface."""
    return PluginManifest(
        id=USAGE_REPORTS_PLUGIN_ID,
        name="Usage Reports",
        version="1.0.0",
        api_version="v1",
        permissions=[
            Permission.USAGE_READ.value,
            Permission.USAGE_ADMIN.value,
        ],
        routers=[
            {
                "name": "usage_reports-api",
                "prefix": "/api/usage",
                "module": "src.api.routes.usage",
                "required_permissions": [
                    Permission.USAGE_READ.value,
                    Permission.USAGE_ADMIN.value,
                ],
                "tags": ["Usage"],
            }
        ],
        frontend={
            "app_tabs": [
                {
                    "id": "usage_reports:usage-tab",
                    "tab": "usage",
                    "path": "/usage",
                    "label": "nav.usage",
                    "panel": "usage_reports:usage-panel",
                    "insert_after": "scheduled-tasks",
                    "order": 620,
                    "permissions": [Permission.USAGE_READ.value],
                    "seo_title": "seo.usage.title",
                    "seo_description": "seo.usage.description",
                    "redirect_to": "/chat",
                    "show_no_permission_toast": True,
                }
            ],
            "app_panels": [
                {
                    "id": "usage_reports:usage-panel",
                    "tab": "usage",
                    "renderer": "usage_reports.UsagePanel",
                }
            ],
            "user_menu_items": [
                {
                    "id": "usage_reports:usage-menu",
                    "path": "/usage",
                    "label": "nav.usage",
                    "icon": "BarChart3",
                    "group": "system",
                    "order": 60,
                    "permissions": [Permission.USAGE_READ.value],
                }
            ],
            "i18n_namespaces": ["usage_reports:usage"],
            "required_permissions": [Permission.USAGE_READ.value],
        },
        resources=[
            {
                "id": "usage_logs",
                "type": "db_collection",
                "scope": "global",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "mongodb",
                    "writer": "core_usage_collection",
                    "manager": "src.infra.usage.storage.UsageStorage",
                    "schema": "src.kernel.schemas.usage.UsageLog",
                },
            },
            {
                "id": "usage_logs.trace_id_unique_idx",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "usage_logs",
                    "fields": "trace_id",
                    "unique": "true",
                },
            },
            {
                "id": "usage_logs.user_started_at_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {"collection": "usage_logs", "fields": "user_id,started_at:-1"},
            },
            {
                "id": "usage_logs.started_at_sort",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {"collection": "usage_logs", "fields": "started_at:-1"},
            },
            {
                "id": "usage_logs.model_started_at_lookup",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {"collection": "usage_logs", "fields": "model,started_at:-1"},
            },
        ],
        enabled_by_default=True,
        core=False,
        install_type=PluginInstallType.SYSTEM_BUILTIN,
    )


def build_advanced_file_viewers_plugin_manifest() -> PluginManifest:
    """Return the static manifest for optional rich document previewers."""
    return PluginManifest(
        id=ADVANCED_FILE_VIEWERS_PLUGIN_ID,
        name="Advanced File Viewers",
        version="1.0.0",
        api_version="v1",
        frontend={
            "file_viewers": [
                "advanced_file_viewers:pdf",
                "advanced_file_viewers:ppt",
                "advanced_file_viewers:word",
                "advanced_file_viewers:excel",
                "advanced_file_viewers:cad",
                "advanced_file_viewers:excalidraw",
                "advanced_file_viewers:html",
                "advanced_file_viewers:markdown",
                "advanced_file_viewers:code",
            ],
            "i18n_namespaces": ["advanced_file_viewers:documents"],
        },
        resources=[
            {
                "id": "document-preview-cache",
                "type": "cache_key",
                "scope": "session",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "producer": "frontend/src/components/documents/documentFetchCache.ts",
                    "purpose": "client-side preview fetch cache",
                },
            },
            {
                "id": "preview-blob-urls",
                "type": "file",
                "scope": "session",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "storage": "browser_object_url",
                    "purpose": "ephemeral rich preview blobs",
                },
            },
        ],
        enabled_by_default=True,
        core=False,
        install_type=PluginInstallType.PREINSTALLED,
    )


def build_github_installer_plugin_manifest() -> PluginManifest:
    """Return the static manifest for GitHub skill import support."""
    return PluginManifest(
        id=GITHUB_INSTALLER_PLUGIN_ID,
        name="GitHub Installer",
        version="1.0.0",
        api_version="v1",
        depends_on=["skill_core"],
        permissions=[Permission.SKILL_READ.value, Permission.SKILL_WRITE.value],
        routers=[
            {
                "name": "github_installer-api",
                "prefix": "/api/github",
                "module": "src.api.routes.github",
                "required_permissions": [
                    Permission.SKILL_READ.value,
                    Permission.SKILL_WRITE.value,
                ],
                "tags": ["GitHub"],
            }
        ],
        frontend={
            "skill_importers": ["github_installer:github-import"],
            "i18n_namespaces": ["github_installer:skills"],
            "required_permissions": [Permission.SKILL_READ.value, Permission.SKILL_WRITE.value],
        },
        resources=[
            {
                "id": "github.com/api/repos/contents",
                "type": "cache_key",
                "scope": "system",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "provider": "github",
                    "purpose": "repository skill preview and install scan",
                },
            },
            {
                "id": "user-skills/{user_id}/{skill_name}",
                "type": "file",
                "scope": "user",
                "retention_policy": "core_owned_do_not_delete",
                "cleanup_strategy": "forbid_delete",
                "metadata": {
                    "writer": "src.api.routes.github.install_github_skills",
                    "owned_by": "skill_core",
                    "reason": "GitHub importer writes Skill core user data and must not delete it during plugin uninstall.",
                },
            },
        ],
        enabled_by_default=True,
        core=False,
        install_type=PluginInstallType.PREINSTALLED,
    )


def build_feishu_connector_plugin_manifest() -> PluginManifest:
    """Return the static manifest for the Feishu channel connector."""
    return PluginManifest(
        id=FEISHU_CONNECTOR_PLUGIN_ID,
        name="Feishu Connector",
        version="1.0.0",
        api_version="v1",
        permissions=[
            Permission.CHANNEL_READ.value,
            Permission.CHANNEL_WRITE.value,
            Permission.CHANNEL_DELETE.value,
        ],
        frontend={
            "channel_connectors": [
                {
                    "id": FEISHU_CONNECTOR_ID,
                    "channel_type": "feishu",
                    "panel_renderer": "feishu_connector.FeishuPanel",
                }
            ],
            "i18n_namespaces": ["feishu_connector:channels"],
            "required_permissions": [Permission.CHANNEL_READ.value],
        },
        runtime_effects=[
            {"action": "enable", "effect": "start_feishu_connector"},
            {"action": "disable", "effect": "stop_feishu_connector"},
        ],
        resources=[
            {
                "id": FEISHU_CONNECTOR_ID,
                "type": "channel_connector",
                "scope": "global",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "channel_type": "feishu",
                    "route_prefix": "/api/channels/feishu",
                    "manager": "src.infra.channel.feishu.manager.FeishuChannelManager",
                    "data_policy": "Connector disable hides/blocks Feishu execution but keeps user channel configs.",
                },
            },
            {
                "id": "feishu_connector:channel-config-change-listener",
                "type": "listener",
                "scope": "system",
                "retention_policy": "manual_review_required",
                "cleanup_strategy": "manual_review",
                "metadata": {
                    "channel": "channel:config:changed",
                    "purpose": "Reload Feishu clients after distributed channel config changes.",
                },
            },
            {
                "id": "user_channel_configs.feishu",
                "type": "db_document",
                "scope": "user",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "collection": "user_channel_configs",
                    "channel_type": "feishu",
                    "reason": "User Feishu app credentials and routing choices must survive connector disable/uninstall dry-run.",
                },
            },
            {
                "id": "user_channel_configs.user_channel_instance_idx",
                "type": "db_index",
                "scope": "global",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "collection": "user_channel_configs",
                    "fields": "user_id,channel_type,instance_id",
                },
            },
            {
                "id": "feishu:registration:*",
                "type": "cache_key",
                "scope": "system",
                "retention_policy": "keep_user_data",
                "cleanup_strategy": "keep",
                "metadata": {
                    "purpose": "One-click Feishu app registration sessions.",
                    "ttl": "ephemeral",
                },
            },
            {
                "id": "feishu:lease:*",
                "type": "cache_key",
                "scope": "system",
                "retention_policy": "archive_metadata",
                "cleanup_strategy": "archive",
                "metadata": {
                    "purpose": "Distributed Feishu long-connection ownership leases.",
                },
            },
            {
                "id": "revealed-files/feishu-delivery",
                "type": "file",
                "scope": "user",
                "retention_policy": "core_owned_do_not_delete",
                "cleanup_strategy": "forbid_delete",
                "metadata": {
                    "owned_by": "core_file_library",
                    "reason": "Feishu may deliver revealed files but file storage remains core-owned user data.",
                },
            },
        ],
        enabled_by_default=True,
        core=False,
        install_type=PluginInstallType.PREINSTALLED,
    )


BUILTIN_PLUGIN_MANIFESTS: tuple[PluginManifest, ...] = (
    build_feedback_plugin_manifest(),
    build_agent_team_plugin_manifest(),
    build_workflow_plugin_manifest(),
    build_image_generation_plugin_manifest(),
    build_audio_transcription_plugin_manifest(),
    build_usage_reports_plugin_manifest(),
    build_advanced_file_viewers_plugin_manifest(),
    build_github_installer_plugin_manifest(),
    build_feishu_connector_plugin_manifest(),
)
