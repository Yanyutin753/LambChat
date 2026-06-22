import asyncio

import pytest

from src.kernel.extensions import (
    PluginInstallType,
    PluginManifest,
    PluginResourceLedger,
    PluginResourceRecord,
    PluginResourceType,
    PluginRuntime,
    PluginRuntimeStateTransitionError,
    PluginRuntimeStatus,
    PluginRuntimeUninstallError,
    PluginUnavailableError,
)


def _plugin(**overrides) -> PluginManifest:
    data = {
        "id": "feedback",
        "name": "Feedback",
        "version": "1.0.0",
        "api_version": "v1",
        "permissions": ["feedback:read"],
    }
    data.update(overrides)
    return PluginManifest(**data)


def test_plugin_runtime_tracks_enabled_disabled_and_error_states() -> None:
    runtime = PluginRuntime(
        [
            _plugin(),
            _plugin(
                id="audio",
                name="Audio",
                permissions=["audio:transcribe"],
                enabled_by_default=False,
            ),
            _plugin(
                id="bad-api",
                name="Bad API",
                permissions=["bad:read"],
                api_version="v0",
            ),
        ]
    )

    assert runtime.get_state("feedback") is not None
    assert runtime.get_state("feedback").status is PluginRuntimeStatus.ENABLED
    assert runtime.get_state("audio").status is PluginRuntimeStatus.DISABLED
    assert runtime.get_state("bad-api").status is PluginRuntimeStatus.ERROR
    assert runtime.get_state("bad-api").issues[0].code == "unsupported_api_version"
    assert runtime.permissions() == ["feedback:read"]
    assert runtime.permissions(enabled_only=False) == [
        "feedback:read",
        "audio:transcribe",
        "bad:read",
    ]


def test_plugin_runtime_validation_errors_do_not_block_valid_plugins() -> None:
    runtime = PluginRuntime(
        [
            _plugin(),
            _plugin(
                id="needs-missing",
                name="Needs Missing",
                depends_on=["missing-plugin"],
                permissions=["not_namespaced"],
            ),
        ]
    )

    assert runtime.is_enabled("feedback") is True
    assert runtime.get_state("needs-missing").status is PluginRuntimeStatus.ERROR
    assert {issue.code for issue in runtime.get_state("needs-missing").issues} == {
        "missing_dependency",
        "invalid_permission_declaration",
    }


def test_plugin_runtime_validates_contribution_namespaces() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/feedback",
                        "module": "plugins.feedback.routes",
                    }
                ],
                tools=[
                    {
                        "name": "feedback_summary",
                        "module": "plugins.feedback.tools",
                        "legacy_ids": ["feedback.summary"],
                    }
                ],
                frontend={
                    "nav_items": ["feedback:nav"],
                    "settings_sections": ["feedback_settings"],
                },
            ),
            _plugin(
                id="bad-namespace",
                name="Bad Namespace",
                permissions=["bad:read"],
                routers=[
                    {
                        "name": "shared-api",
                        "prefix": "/api/shared",
                        "module": "plugins.bad.routes",
                    }
                ],
                tools=[{"name": "summarize", "module": "plugins.bad.tools"}],
                frontend={"nav_items": ["shared-nav"]},
            ),
        ]
    )

    assert runtime.get_state("feedback").status is PluginRuntimeStatus.ENABLED
    state = runtime.get_state("bad-namespace")
    assert state.status is PluginRuntimeStatus.ERROR
    assert state.issues[-1].code == "invalid_contribution_namespace"
    assert "shared-api" in state.issues[-1].message
    assert "summarize" in state.issues[-1].message
    assert "shared-nav" in state.issues[-1].message


def test_plugin_manifest_rejects_foreign_structured_frontend_contribution_id() -> None:
    with pytest.raises(ValueError, match="owned by plugin feedback"):
        _plugin(
            frontend={
                "message_actions": [
                    {
                        "id": "other_plugin:message-action",
                        "target": "assistant_message",
                        "renderer": "feedback.FeedbackButtons",
                    }
                ]
            }
        )


def test_plugin_manifest_rejects_foreign_structured_frontend_renderer_reference() -> None:
    with pytest.raises(
        ValueError, match="renderers and contribution references must be owned by plugin feedback"
    ):
        _plugin(
            frontend={
                "message_actions": [
                    {
                        "id": "feedback:message-action",
                        "target": "assistant_message",
                        "renderer": "other_plugin.FeedbackButtons",
                    }
                ]
            }
        )


def test_plugin_manifest_rejects_scoped_option_binding_without_setting() -> None:
    with pytest.raises(ValueError, match="scheduled_task:SELECTED_TEAM_ID"):
        _plugin(
            id="agent_team",
            name="Agent Team",
            frontend={
                "scheduled_task_options": [
                    {
                        "key": "SELECTED_TEAM_ID",
                        "type": "string",
                        "label": "Selected team",
                        "legacy_payload_keys": ["team_id"],
                    }
                ]
            },
        )


def test_plugin_runtime_duplicate_ids_enter_error_state() -> None:
    runtime = PluginRuntime(
        [
            _plugin(),
            _plugin(name="Duplicate Feedback", permissions=["feedback:write"]),
        ]
    )

    state = runtime.get_state("feedback")

    assert state is not None
    assert state.status is PluginRuntimeStatus.ERROR
    assert [issue.code for issue in state.issues] == ["duplicate_plugin_id"]
    assert runtime.permissions() == []


def test_plugin_runtime_guard_rejects_missing_disabled_and_error_plugins() -> None:
    runtime = PluginRuntime(
        [
            _plugin(),
            _plugin(id="disabled", name="Disabled", enabled_by_default=False),
            _plugin(id="bad", name="Bad", api_version="v0"),
        ]
    )

    runtime.ensure_enabled("feedback")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_enabled("missing")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_enabled("disabled")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_enabled("bad")


def test_plugin_runtime_guards_plugin_owned_agent_entries() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                id="agent_team",
                name="Agent Team",
                permissions=["team:read"],
                agents=[
                    {
                        "id": "team",
                        "module": "src.agents.team_agent.graph.TeamAgent",
                        "required_permissions": ["team:read"],
                    }
                ],
            )
        ]
    )

    assert runtime.plugin_for_agent("team") == "agent_team"
    assert runtime.ensure_agent_available("team").plugin_id == "agent_team"
    assert runtime.ensure_agent_available("search") is None

    runtime.disable_plugin("agent_team")

    with pytest.raises(PluginUnavailableError):
        runtime.ensure_agent_available("team")
    assert runtime.plugin_for_agent("team") == "agent_team"


def test_plugin_runtime_supports_controlled_enable_disable_without_uninstalling() -> None:
    runtime = PluginRuntime([_plugin()])

    disabled = runtime.disable_plugin("feedback")
    assert disabled.status is PluginRuntimeStatus.DISABLED
    assert disabled.manifest is not None
    assert runtime.is_enabled("feedback") is False
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_enabled("feedback")

    enabled = runtime.enable_plugin("feedback")
    assert enabled.status is PluginRuntimeStatus.ENABLED
    assert runtime.is_enabled("feedback") is True
    runtime.ensure_enabled("feedback")


def test_plugin_runtime_only_uninstalls_uninstallable_plugin_types() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                id="system_plugin",
                name="System Plugin",
                permissions=["system_plugin:read"],
                install_type=PluginInstallType.SYSTEM_BUILTIN,
            ),
            _plugin(
                id="preinstalled_plugin",
                name="Preinstalled Plugin",
                permissions=["preinstalled_plugin:read"],
                install_type=PluginInstallType.PREINSTALLED,
            ),
        ]
    )

    assert runtime.get_state("system_plugin").manifest.uninstallable is False
    assert runtime.get_state("preinstalled_plugin").manifest.uninstallable is True
    with pytest.raises(PluginRuntimeUninstallError):
        runtime.uninstall_plugin("system_plugin")

    state = runtime.uninstall_plugin("preinstalled_plugin")

    assert state.status is PluginRuntimeStatus.UNINSTALLED
    assert state.executable is False


def test_plugin_runtime_repeated_disable_is_idempotent_and_keeps_resources() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                tools=[{"name": "feedback_summary", "module": "plugins.feedback.tools"}],
                scheduler_jobs=["feedback.sync"],
            )
        ]
    )

    first = runtime.disable_plugin("feedback")
    second = runtime.disable_plugin("feedback")

    assert first is second
    assert second.status is PluginRuntimeStatus.DISABLED
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.TOOL,
            resource_id="feedback_summary",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SCHEDULER_JOB,
            resource_id="feedback.sync",
        )
        is not None
    )


def test_plugin_runtime_applies_stored_enabled_disabled_overrides() -> None:
    runtime = PluginRuntime([_plugin()])

    state = runtime.apply_stored_status("feedback", PluginRuntimeStatus.DISABLED)
    assert state.status is PluginRuntimeStatus.DISABLED
    assert state.state_source == "stored_override"
    assert runtime.is_enabled("feedback") is False

    state = runtime.apply_stored_status("feedback", "enabled")
    assert state.status is PluginRuntimeStatus.ENABLED
    assert state.state_source == "stored_override"
    assert runtime.is_enabled("feedback") is True


def test_plugin_runtime_controlled_state_changes_reject_missing_and_error_plugins() -> None:
    runtime = PluginRuntime([_plugin(id="bad", name="Bad", api_version="v0")])

    with pytest.raises(PluginRuntimeStateTransitionError):
        runtime.enable_plugin("missing")
    with pytest.raises(PluginRuntimeStateTransitionError):
        runtime.disable_plugin("missing")
    with pytest.raises(PluginRuntimeStateTransitionError):
        runtime.enable_plugin("bad")
    with pytest.raises(PluginRuntimeStateTransitionError):
        runtime.disable_plugin("bad")


def test_plugin_runtime_collects_only_enabled_lifecycle_hooks() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                lifespan_hooks=[
                    {
                        "name": "late",
                        "module": "plugins.feedback.hooks:late",
                        "phase": "startup",
                        "order": 20,
                    },
                    {
                        "name": "early",
                        "module": "plugins.feedback.hooks:early",
                        "phase": "startup",
                        "order": 10,
                    },
                ]
            ),
            _plugin(
                id="disabled",
                name="Disabled",
                enabled_by_default=False,
                lifespan_hooks=[
                    {
                        "name": "disabled",
                        "module": "plugins.disabled.hooks:start",
                        "phase": "startup",
                    }
                ],
            ),
        ]
    )

    assert [hook.name for hook in runtime.lifecycle_hooks(phase="startup")] == [
        "early",
        "late",
    ]
    assert [hook.name for hook in runtime.lifecycle_hooks(phase="startup", enabled_only=False)] == [
        "early",
        "late",
        "disabled",
    ]


def test_plugin_runtime_exposes_route_and_tool_declarations_for_executable_plugins() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/plugins/feedback",
                        "module": "plugins.feedback.routes",
                    }
                ],
                tools=[
                    {
                        "name": "feedback_summary",
                        "module": "plugins.feedback.tools",
                    }
                ],
            ),
            _plugin(
                id="disabled",
                name="Disabled",
                enabled_by_default=False,
                routers=[
                    {
                        "name": "disabled-api",
                        "prefix": "/api/plugins/disabled",
                        "module": "plugins.disabled.routes",
                    }
                ],
                tools=[
                    {
                        "name": "disabled_tool",
                        "module": "plugins.disabled.tools",
                    }
                ],
            ),
        ]
    )

    assert [(route.plugin_id, route.name) for route in runtime.routes()] == [
        ("feedback", "feedback-api")
    ]
    assert [(tool.plugin_id, tool.name) for tool in runtime.tools()] == [
        ("feedback", "feedback_summary")
    ]


def test_plugin_runtime_guards_plugin_tools_by_runtime_state() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                tools=[
                    {
                        "name": "feedback_summary",
                        "module": "plugins.feedback.tools",
                        "legacy_ids": ["feedback.summary"],
                    }
                ],
            ),
            _plugin(
                id="disabled",
                name="Disabled",
                enabled_by_default=False,
                tools=[
                    {
                        "name": "disabled_tool",
                        "module": "plugins.disabled.tools",
                    }
                ],
            ),
        ]
    )

    registration = runtime.ensure_tool_available("feedback_summary")

    assert registration.plugin_id == "feedback"
    assert runtime.ensure_tool_available("feedback.summary") == registration
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_tool_available("disabled_tool")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_tool_available("missing.tool")

    runtime.disable_plugin("feedback")

    with pytest.raises(PluginUnavailableError):
        runtime.ensure_tool_available("feedback_summary")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_tool_available("feedback.summary")


def test_plugin_runtime_filters_and_guards_scheduler_jobs_and_listeners() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                scheduler_jobs=["feedback.sync"],
                event_listeners=["feedback.package-listener"],
                resources=[
                    {
                        "id": "feedback.listener",
                        "type": "listener",
                        "retention_policy": "manual_review_required",
                        "cleanup_strategy": "manual_review",
                    }
                ],
            ),
            _plugin(
                id="disabled",
                name="Disabled",
                permissions=["disabled:read"],
                enabled_by_default=False,
                scheduler_jobs=["disabled.sync"],
                event_listeners=["disabled.package-listener"],
                resources=[
                    {
                        "id": "disabled.listener",
                        "type": "listener",
                        "retention_policy": "manual_review_required",
                        "cleanup_strategy": "manual_review",
                    }
                ],
            ),
        ]
    )

    assert runtime.scheduler_jobs() == ["feedback.sync"]
    assert runtime.scheduler_jobs(enabled_only=False) == [
        "feedback.sync",
        "disabled.sync",
    ]
    assert [record.resource_id for record in runtime.listeners()] == [
        "feedback.package-listener",
        "feedback.listener",
    ]
    assert [record.resource_id for record in runtime.listeners(enabled_only=False)] == [
        "feedback.package-listener",
        "feedback.listener",
        "disabled.package-listener",
        "disabled.listener",
    ]
    assert runtime.ensure_scheduler_job_available("feedback.sync").plugin_id == "feedback"
    assert runtime.ensure_listener_available("feedback.package-listener").plugin_id == "feedback"
    assert runtime.ensure_listener_available("feedback.listener").plugin_id == "feedback"

    with pytest.raises(PluginUnavailableError):
        runtime.ensure_scheduler_job_available("disabled.sync")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_listener_available("disabled.package-listener")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_listener_available("disabled.listener")

    runtime.disable_plugin("feedback")

    assert runtime.scheduler_jobs() == []
    assert runtime.listeners() == []
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_scheduler_job_available("feedback.sync")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_listener_available("feedback.package-listener")
    with pytest.raises(PluginUnavailableError):
        runtime.ensure_listener_available("feedback.listener")


def test_plugin_runtime_builds_resource_ledger_from_manifest_declarations() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                settings=[
                    {
                        "key": "DEFAULT_FEEDBACK_VIEW",
                        "type": "string",
                        "scope": "project",
                    },
                    {
                        "key": "ACTIVE_FEEDBACK_FILTER",
                        "type": "string",
                        "scope": "session",
                    },
                    {
                        "key": "ACTIVE_FEEDBACK_CHANNEL",
                        "type": "string",
                        "scope": "channel",
                    },
                    {
                        "key": "ACTIVE_FEEDBACK_TASK",
                        "type": "string",
                        "scope": "scheduled_task",
                    },
                ],
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/plugins/feedback",
                        "module": "plugins.feedback.routes",
                    }
                ],
                tools=[
                    {
                        "name": "feedback_summary",
                        "module": "plugins.feedback.tools",
                    }
                ],
                frontend={
                    "routes": ["feedback-route"],
                    "panels": ["feedback-panel"],
                    "nav_items": ["feedback-nav"],
                    "app_tabs": [
                        {
                            "id": "feedback:tab",
                            "tab": "feedback",
                            "path": "/feedback",
                        }
                    ],
                    "app_panels": [
                        {
                            "id": "feedback:panel",
                            "tab": "feedback",
                            "renderer": "feedback.Panel",
                        }
                    ],
                    "sidebar_items": [
                        {
                            "id": "feedback:sidebar",
                            "path": "/feedback",
                            "label": "feedback.nav",
                        }
                    ],
                    "user_menu_items": [
                        {
                            "id": "feedback:user-menu",
                            "path": "/feedback",
                            "label": "feedback.nav",
                            "group": "system",
                        }
                    ],
                    "chat_input_options": [
                        {
                            "id": "feedback:quick-reply",
                            "label": "feedback.quickReply",
                            "panel": "feedback:quick-reply-panel",
                        }
                    ],
                    "chat_input_panels": [
                        {
                            "id": "feedback:quick-reply-panel",
                            "renderer": "feedback.QuickReplyPanel",
                        }
                    ],
                    "mention_providers": [
                        {
                            "id": "feedback:mentions",
                            "mode": "feedback",
                            "provider": "feedback.search",
                        }
                    ],
                    "agent_categories": [
                        {
                            "id": "feedback:agents",
                            "label": "feedback.agents",
                        }
                    ],
                    "project_options": [
                        {
                            "key": "DEFAULT_FEEDBACK_VIEW",
                            "type": "string",
                            "label": "feedback.defaultView",
                        }
                    ],
                    "session_options": [
                        {
                            "key": "ACTIVE_FEEDBACK_FILTER",
                            "type": "string",
                            "label": "feedback.activeFilter",
                        }
                    ],
                    "channel_options": [
                        {
                            "key": "ACTIVE_FEEDBACK_CHANNEL",
                            "type": "string",
                            "label": "feedback.activeChannel",
                        }
                    ],
                    "scheduled_task_options": [
                        {
                            "key": "ACTIVE_FEEDBACK_TASK",
                            "type": "string",
                            "label": "feedback.activeTask",
                        }
                    ],
                    "i18n_namespaces": ["feedback"],
                },
                scheduler_jobs=["feedback-sync"],
                event_listeners=["feedback-listener"],
                migrations=["feedback-v1"],
            )
        ]
    )

    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.BACKEND_ROUTE,
            resource_id="feedback-api",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.TOOL,
            resource_id="feedback_summary",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.PERMISSION,
            resource_id="feedback:read",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.FRONTEND_ROUTE,
            resource_id="feedback-route",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.APP_TAB,
            resource_id="feedback:tab",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.APP_PANEL,
            resource_id="feedback:panel",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SIDEBAR_ITEM,
            resource_id="feedback:sidebar",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.USER_MENU_ITEM,
            resource_id="feedback:user-menu",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.CHAT_INPUT_OPTION,
            resource_id="feedback:quick-reply",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.CHAT_INPUT_PANEL,
            resource_id="feedback:quick-reply-panel",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.MENTION_PROVIDER,
            resource_id="feedback:mentions",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.AGENT_CATEGORY,
            resource_id="feedback:agents",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.PROJECT_OPTION,
            resource_id="feedback.DEFAULT_FEEDBACK_VIEW",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SESSION_OPTION,
            resource_id="feedback.ACTIVE_FEEDBACK_FILTER",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.CHANNEL_OPTION,
            resource_id="feedback.ACTIVE_FEEDBACK_CHANNEL",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SCHEDULED_TASK_OPTION,
            resource_id="feedback.ACTIVE_FEEDBACK_TASK",
        )
        is not None
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SETTING,
            resource_id="feedback.project.DEFAULT_FEEDBACK_VIEW",
        ).scope.value
        == "project"
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SETTING,
            resource_id="feedback.session.ACTIVE_FEEDBACK_FILTER",
        ).scope.value
        == "session"
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SETTING,
            resource_id="feedback.channel.ACTIVE_FEEDBACK_CHANNEL",
        ).scope.value
        == "channel"
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SETTING,
            resource_id="feedback.scheduled_task.ACTIVE_FEEDBACK_TASK",
        ).scope.value
        == "scheduled_task"
    )
    assert (
        runtime.resource_ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.LISTENER,
            resource_id="feedback-listener",
        )
        is not None
    )


def test_plugin_runtime_keeps_same_setting_key_distinct_across_scopes() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                id="agent_team",
                name="Agent Team",
                permissions=["agent_team:read"],
                settings=[
                    {"key": "SELECTED_TEAM_ID", "type": "string", "scope": "session"},
                    {"key": "SELECTED_TEAM_ID", "type": "string", "scope": "channel"},
                    {"key": "SELECTED_TEAM_ID", "type": "string", "scope": "scheduled_task"},
                ],
            )
        ]
    )

    setting_records = runtime.resource_ledger.list(
        plugin_id="agent_team",
        resource_type=PluginResourceType.SETTING,
    )

    assert {(record.resource_id, record.scope.value) for record in setting_records} == {
        ("agent_team.session.SELECTED_TEAM_ID", "session"),
        ("agent_team.channel.SELECTED_TEAM_ID", "channel"),
        ("agent_team.scheduled_task.SELECTED_TEAM_ID", "scheduled_task"),
    }


def test_plugin_runtime_resource_conflicts_enter_plugin_error_state() -> None:
    ledger = PluginResourceLedger(
        [
            PluginResourceRecord(
                plugin_id="existing",
                resource_id="audio-api",
                resource_type=PluginResourceType.BACKEND_ROUTE,
            )
        ]
    )
    runtime = PluginRuntime(
        [
            _plugin(
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/plugins/feedback",
                        "module": "plugins.feedback.routes",
                    }
                ]
            ),
            _plugin(
                id="audio",
                name="Audio",
                permissions=["audio:read"],
                routers=[
                    {
                        "name": "audio-api",
                        "prefix": "/api/plugins/audio",
                        "module": "plugins.audio.routes",
                    }
                ],
            ),
        ],
        resource_ledger=ledger,
    )

    assert runtime.get_state("feedback").status is PluginRuntimeStatus.ENABLED
    assert runtime.get_state("audio").status is PluginRuntimeStatus.ERROR
    assert runtime.get_state("audio").issues[-1].code == "resource_conflict"


@pytest.mark.asyncio
async def test_plugin_runtime_lifecycle_execution_isolates_hook_failures() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                lifespan_hooks=[
                    {
                        "name": "ok",
                        "module": "plugins.feedback.hooks:ok",
                        "phase": "startup",
                        "order": 10,
                    }
                ]
            ),
            _plugin(
                id="broken",
                name="Broken",
                permissions=["broken:read"],
                lifespan_hooks=[
                    {
                        "name": "boom",
                        "module": "plugins.broken.hooks:boom",
                        "phase": "startup",
                        "order": 20,
                    }
                ],
            ),
        ]
    )

    async def executor(hook):
        if hook.plugin_id == "broken":
            raise RuntimeError("hook exploded")

    results = await runtime.execute_lifecycle_hooks(
        phase="startup",
        executor=executor,
        timeout_seconds=1,
    )

    assert [(result.plugin_id, result.status) for result in results] == [
        ("feedback", "succeeded"),
        ("broken", "failed"),
    ]
    assert runtime.get_state("feedback").status is PluginRuntimeStatus.ENABLED
    assert runtime.get_state("broken").status is PluginRuntimeStatus.ERROR
    assert runtime.get_state("broken").issues[-1].code == "hook_failed"


@pytest.mark.asyncio
async def test_plugin_runtime_lifecycle_execution_records_timeouts() -> None:
    runtime = PluginRuntime(
        [
            _plugin(
                lifespan_hooks=[
                    {
                        "name": "slow",
                        "module": "plugins.feedback.hooks:slow",
                        "phase": "startup",
                    }
                ]
            )
        ]
    )

    async def executor(_hook):
        await asyncio.sleep(0.05)

    results = await runtime.execute_lifecycle_hooks(
        phase="startup",
        executor=executor,
        timeout_seconds=0.001,
    )

    assert [(result.plugin_id, result.status) for result in results] == [("feedback", "timeout")]
    assert runtime.get_state("feedback").status is PluginRuntimeStatus.ERROR
    assert runtime.get_state("feedback").issues[-1].code == "hook_timeout"
