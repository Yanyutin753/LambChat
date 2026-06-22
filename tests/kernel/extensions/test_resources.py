import pytest

from src.kernel.extensions import (
    PluginResourceCleanupStrategy,
    PluginResourceConflictError,
    PluginResourceLedger,
    PluginResourceRecord,
    PluginResourceRetentionPolicy,
    PluginResourceScope,
    PluginResourceType,
)


def test_resource_type_accepts_message_action_declarations() -> None:
    record = PluginResourceRecord(
        plugin_id="feedback",
        resource_id="feedback:message-feedback",
        resource_type=PluginResourceType("message_action"),
    )

    assert record.resource_type is PluginResourceType.MESSAGE_ACTION


def test_resource_ledger_registers_and_queries_plugin_resources() -> None:
    ledger = PluginResourceLedger()

    record = ledger.register(
        PluginResourceRecord(
            plugin_id="feedback",
            resource_id="feedback-api",
            resource_type=PluginResourceType.BACKEND_ROUTE,
            scope=PluginResourceScope.GLOBAL,
            created_by_plugin_version="1.0.0",
            retention_policy=PluginResourceRetentionPolicy.KEEP_USER_DATA,
            cleanup_strategy=PluginResourceCleanupStrategy.KEEP,
        )
    )

    assert record.plugin_id == "feedback"
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type="backend_route",
            resource_id="feedback-api",
        )
        == record
    )
    assert ledger.list(plugin_id="feedback") == [record]
    assert ledger.list(resource_type="backend_route") == [record]
    assert ledger.list(scope="global") == [record]


def test_resource_ledger_rejects_cross_plugin_resource_conflicts() -> None:
    ledger = PluginResourceLedger(
        [
            PluginResourceRecord(
                plugin_id="feedback",
                resource_id="shared-route",
                resource_type=PluginResourceType.BACKEND_ROUTE,
            )
        ]
    )

    with pytest.raises(PluginResourceConflictError):
        ledger.register(
            PluginResourceRecord(
                plugin_id="audio",
                resource_id="shared-route",
                resource_type=PluginResourceType.BACKEND_ROUTE,
            )
        )


def test_resource_ledger_allows_shared_permission_declarations() -> None:
    ledger = PluginResourceLedger()

    first = ledger.register(
        PluginResourceRecord(
            plugin_id="image_generation",
            resource_id="mcp:read",
            resource_type=PluginResourceType.PERMISSION,
        )
    )
    second = ledger.register(
        PluginResourceRecord(
            plugin_id="audio_transcription",
            resource_id="mcp:read",
            resource_type=PluginResourceType.PERMISSION,
        )
    )

    assert first.plugin_id == "image_generation"
    assert second.plugin_id == "audio_transcription"
    assert len(ledger.list(resource_type=PluginResourceType.PERMISSION)) == 2


def test_resource_ledger_registering_same_plugin_resource_is_idempotent() -> None:
    ledger = PluginResourceLedger()
    first = ledger.register(
        PluginResourceRecord(
            plugin_id="feedback",
            resource_id="feedback-api",
            resource_type=PluginResourceType.BACKEND_ROUTE,
        )
    )
    second = ledger.register(
        PluginResourceRecord(
            plugin_id="feedback",
            resource_id="feedback-api",
            resource_type=PluginResourceType.BACKEND_ROUTE,
        )
    )

    assert len(ledger.list(plugin_id="feedback")) == 1
    assert second.resource_id == first.resource_id
    assert second.last_seen_at >= first.last_seen_at


def test_resource_ledger_registers_manifest_declarations_with_cleanup_policies() -> None:
    ledger = PluginResourceLedger()

    records = ledger.register_manifest_resources(
        plugin_id="feedback",
        plugin_version="1.0.0",
        backend_routes=["feedback-api"],
        frontend_routes=["feedback-route"],
        panels=["feedback-panel"],
        nav_items=["feedback-nav"],
        tools=["feedback_summary"],
        chat_input_options=["feedback:quick-reply"],
        chat_input_panels=["feedback:quick-reply-panel"],
        mention_providers=["feedback:mentions"],
        project_options=["feedback.DEFAULT_PROJECT"],
        session_options=["feedback.SELECTED_SESSION"],
        channel_options=["feedback.SELECTED_CHANNEL"],
        scheduled_task_options=["feedback.SELECTED_TASK"],
        permissions=["feedback:read"],
        settings=[
            "feedback:settings",
            ("feedback.project.DEFAULT_PROJECT", "project"),
            ("feedback.channel.SELECTED_CHANNEL", "channel"),
            ("feedback.scheduled_task.SELECTED_TASK", "scheduled_task"),
        ],
        env_keys=["FEEDBACK_TOKEN"],
        scheduler_jobs=["feedback-sync"],
        event_listeners=["feedback-listener"],
        migrations=["feedback-v1"],
        i18n_namespaces=["feedback"],
    )

    assert len(records) == 22
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.PROJECT_OPTION,
            resource_id="feedback.DEFAULT_PROJECT",
        ).cleanup_strategy
        is PluginResourceCleanupStrategy.KEEP
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SESSION_OPTION,
            resource_id="feedback.SELECTED_SESSION",
        ).cleanup_strategy
        is PluginResourceCleanupStrategy.KEEP
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.CHANNEL_OPTION,
            resource_id="feedback.SELECTED_CHANNEL",
        ).cleanup_strategy
        is PluginResourceCleanupStrategy.KEEP
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SCHEDULED_TASK_OPTION,
            resource_id="feedback.SELECTED_TASK",
        ).cleanup_strategy
        is PluginResourceCleanupStrategy.KEEP
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.PERMISSION,
            resource_id="feedback:read",
        ).cleanup_strategy
        is PluginResourceCleanupStrategy.ARCHIVE
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SCHEDULER_JOB,
            resource_id="feedback-sync",
        ).retention_policy
        is PluginResourceRetentionPolicy.MANUAL_REVIEW_REQUIRED
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.LISTENER,
            resource_id="feedback-listener",
        ).retention_policy
        is PluginResourceRetentionPolicy.MANUAL_REVIEW_REQUIRED
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SETTING,
            resource_id="feedback:settings",
        ).scope
        is PluginResourceScope.GLOBAL
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SETTING,
            resource_id="feedback.project.DEFAULT_PROJECT",
        ).scope
        is PluginResourceScope.PROJECT
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SETTING,
            resource_id="feedback.channel.SELECTED_CHANNEL",
        ).scope
        is PluginResourceScope.CHANNEL
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.SETTING,
            resource_id="feedback.scheduled_task.SELECTED_TASK",
        ).scope
        is PluginResourceScope.SCHEDULED_TASK
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.TOOL,
            resource_id="feedback_summary",
        ).created_by_plugin_version
        == "1.0.0"
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.CHAT_INPUT_OPTION,
            resource_id="feedback:quick-reply",
        )
        is not None
    )
    assert (
        ledger.get(
            plugin_id="feedback",
            resource_type=PluginResourceType.MENTION_PROVIDER,
            resource_id="feedback:mentions",
        )
        is not None
    )


def test_resource_ledger_keeps_scoped_setting_resource_ids_distinct() -> None:
    ledger = PluginResourceLedger()

    records = ledger.register_manifest_resources(
        plugin_id="agent_team",
        plugin_version="1.0.0",
        settings=[
            ("agent_team.session.SELECTED_TEAM_ID", "session"),
            ("agent_team.channel.SELECTED_TEAM_ID", "channel"),
            ("agent_team.scheduled_task.SELECTED_TEAM_ID", "scheduled_task"),
        ],
    )

    assert len(records) == 3
    assert {
        (record.resource_id, record.scope)
        for record in ledger.list(plugin_id="agent_team", resource_type=PluginResourceType.SETTING)
    } == {
        ("agent_team.session.SELECTED_TEAM_ID", PluginResourceScope.SESSION),
        ("agent_team.channel.SELECTED_TEAM_ID", PluginResourceScope.CHANNEL),
        ("agent_team.scheduled_task.SELECTED_TEAM_ID", PluginResourceScope.SCHEDULED_TASK),
    }
