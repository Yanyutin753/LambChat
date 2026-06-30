from datetime import UTC, datetime, timedelta

from src.kernel.extensions import (
    PluginDryRunAction,
    PluginResourceCleanupStrategy,
    PluginResourceLedger,
    PluginResourceRecord,
    PluginResourceRetentionPolicy,
    PluginResourceScope,
    PluginResourceType,
    build_uninstall_dry_run,
    validate_uninstall_dry_run,
)


def _record(resource_id: str, cleanup_strategy: PluginResourceCleanupStrategy):
    return PluginResourceRecord(
        plugin_id="feedback",
        resource_id=resource_id,
        resource_type=PluginResourceType.BACKEND_ROUTE,
        cleanup_strategy=cleanup_strategy,
        retention_policy={
            PluginResourceCleanupStrategy.DELETE: PluginResourceRetentionPolicy.DELETE_ON_UNINSTALL,
            PluginResourceCleanupStrategy.KEEP: PluginResourceRetentionPolicy.KEEP_USER_DATA,
            PluginResourceCleanupStrategy.ARCHIVE: PluginResourceRetentionPolicy.ARCHIVE_METADATA,
            PluginResourceCleanupStrategy.MANUAL_REVIEW: PluginResourceRetentionPolicy.MANUAL_REVIEW_REQUIRED,
            PluginResourceCleanupStrategy.FORBID_DELETE: PluginResourceRetentionPolicy.CORE_OWNED_DO_NOT_DELETE,
        }[cleanup_strategy],
    )


def test_uninstall_dry_run_classifies_resource_cleanup_actions() -> None:
    ledger = PluginResourceLedger(
        [
            _record("delete-me", PluginResourceCleanupStrategy.DELETE),
            _record("keep-me", PluginResourceCleanupStrategy.KEEP),
            _record("archive-me", PluginResourceCleanupStrategy.ARCHIVE),
            _record("review-me", PluginResourceCleanupStrategy.MANUAL_REVIEW),
            _record("core-owned", PluginResourceCleanupStrategy.FORBID_DELETE),
        ]
    )

    dry_run = build_uninstall_dry_run(plugin_id="feedback", ledger=ledger)

    assert dry_run.resource_count == 5
    assert [resource.resource_id for resource in dry_run.will_delete] == ["delete-me"]
    assert [resource.resource_id for resource in dry_run.will_keep] == ["keep-me"]
    assert [resource.resource_id for resource in dry_run.will_archive] == ["archive-me"]
    assert [resource.resource_id for resource in dry_run.needs_manual_review] == [
        "review-me"
    ]
    assert [resource.resource_id for resource in dry_run.forbidden_to_delete] == [
        "core-owned"
    ]
    assert dry_run.will_delete[0].requires_confirmation is True
    assert dry_run.will_delete[0].irreversible is True
    assert dry_run.forbidden_to_delete[0].requires_confirmation is True
    assert dry_run.snapshot_id
    assert dry_run.resource_fingerprint
    assert dry_run.expires_at > dry_run.created_at


def test_uninstall_dry_run_empty_ledger_warns_and_does_not_delete() -> None:
    dry_run = build_uninstall_dry_run(plugin_id="missing", ledger=PluginResourceLedger())

    assert dry_run.resource_count == 0
    assert dry_run.will_delete == []
    assert dry_run.warnings == ["No resource ledger entries were found for this plugin."]
    assert dry_run.rollback_notes == [
        "Uninstall execution must use this dry-run snapshot and only process plugin-owned resources."
    ]


def test_uninstall_dry_run_only_lists_requested_plugin_resources() -> None:
    ledger = PluginResourceLedger(
        [
            _record("feedback-api", PluginResourceCleanupStrategy.KEEP),
            PluginResourceRecord(
                plugin_id="audio",
                resource_id="audio-api",
                resource_type=PluginResourceType.BACKEND_ROUTE,
                cleanup_strategy=PluginResourceCleanupStrategy.DELETE,
                retention_policy=PluginResourceRetentionPolicy.DELETE_ON_UNINSTALL,
            ),
        ]
    )

    dry_run = build_uninstall_dry_run(plugin_id="feedback", ledger=ledger)

    assert [resource.plugin_id for resource in dry_run.resources] == ["feedback"]
    assert [resource.action for resource in dry_run.resources] == [PluginDryRunAction.KEEP]


def test_uninstall_dry_run_archives_scoped_plugin_settings_without_delete() -> None:
    ledger = PluginResourceLedger(
        [
            PluginResourceRecord(
                plugin_id="agent_team",
                resource_id="agent_team.project.DEFAULT_TEAM_ID",
                resource_type=PluginResourceType.SETTING,
                scope=PluginResourceScope.PROJECT,
                cleanup_strategy=PluginResourceCleanupStrategy.ARCHIVE,
                retention_policy=PluginResourceRetentionPolicy.ARCHIVE_METADATA,
            ),
            PluginResourceRecord(
                plugin_id="agent_team",
                resource_id="agent_team.session.SELECTED_TEAM_ID",
                resource_type=PluginResourceType.SETTING,
                scope=PluginResourceScope.SESSION,
                cleanup_strategy=PluginResourceCleanupStrategy.ARCHIVE,
                retention_policy=PluginResourceRetentionPolicy.ARCHIVE_METADATA,
            ),
            PluginResourceRecord(
                plugin_id="agent_team",
                resource_id="agent_team.channel.SELECTED_TEAM_ID",
                resource_type=PluginResourceType.SETTING,
                scope=PluginResourceScope.CHANNEL,
                cleanup_strategy=PluginResourceCleanupStrategy.ARCHIVE,
                retention_policy=PluginResourceRetentionPolicy.ARCHIVE_METADATA,
            ),
            PluginResourceRecord(
                plugin_id="agent_team",
                resource_id="agent_team.scheduled_task.SELECTED_TEAM_ID",
                resource_type=PluginResourceType.SETTING,
                scope=PluginResourceScope.SCHEDULED_TASK,
                cleanup_strategy=PluginResourceCleanupStrategy.ARCHIVE,
                retention_policy=PluginResourceRetentionPolicy.ARCHIVE_METADATA,
            ),
        ]
    )

    dry_run = build_uninstall_dry_run(plugin_id="agent_team", ledger=ledger)
    resources_by_id = {resource.resource_id: resource for resource in dry_run.resources}

    assert dry_run.will_delete == []
    assert dry_run.needs_manual_review == []
    assert resources_by_id["agent_team.project.DEFAULT_TEAM_ID"].action is PluginDryRunAction.ARCHIVE
    assert resources_by_id["agent_team.project.DEFAULT_TEAM_ID"].scope == "project"
    assert resources_by_id["agent_team.session.SELECTED_TEAM_ID"].action is PluginDryRunAction.ARCHIVE
    assert resources_by_id["agent_team.session.SELECTED_TEAM_ID"].scope == "session"
    assert resources_by_id["agent_team.channel.SELECTED_TEAM_ID"].action is PluginDryRunAction.ARCHIVE
    assert resources_by_id["agent_team.channel.SELECTED_TEAM_ID"].scope == "channel"
    assert resources_by_id["agent_team.scheduled_task.SELECTED_TEAM_ID"].action is PluginDryRunAction.ARCHIVE
    assert resources_by_id["agent_team.scheduled_task.SELECTED_TEAM_ID"].scope == "scheduled_task"


def test_uninstall_dry_run_validation_blocks_missing_snapshot() -> None:
    validation = validate_uninstall_dry_run(
        None,
        plugin_id="feedback",
        ledger=PluginResourceLedger([_record("keep-me", PluginResourceCleanupStrategy.KEEP)]),
    )

    assert validation.allowed is False
    assert validation.blockers == ["dry_run_required"]
    assert validation.snapshot_id is None


def test_uninstall_dry_run_validation_blocks_expired_snapshot() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    ledger = PluginResourceLedger([_record("keep-me", PluginResourceCleanupStrategy.KEEP)])
    dry_run = build_uninstall_dry_run(
        plugin_id="feedback",
        ledger=ledger,
        now=now,
        ttl_seconds=60,
    )

    validation = validate_uninstall_dry_run(
        dry_run,
        plugin_id="feedback",
        ledger=ledger,
        now=now + timedelta(seconds=61),
    )

    assert validation.allowed is False
    assert validation.expired is True
    assert "dry_run_expired" in validation.blockers


def test_uninstall_dry_run_validation_blocks_resource_changes() -> None:
    ledger = PluginResourceLedger([_record("keep-me", PluginResourceCleanupStrategy.KEEP)])
    dry_run = build_uninstall_dry_run(plugin_id="feedback", ledger=ledger)

    ledger.register(_record("archive-me", PluginResourceCleanupStrategy.ARCHIVE))
    validation = validate_uninstall_dry_run(
        dry_run,
        plugin_id="feedback",
        ledger=ledger,
    )

    assert validation.allowed is False
    assert validation.resource_changed is True
    assert "dry_run_resource_fingerprint_changed" in validation.blockers


def test_uninstall_dry_run_validation_blocks_forbidden_and_manual_resources() -> None:
    ledger = PluginResourceLedger(
        [
            _record("review-me", PluginResourceCleanupStrategy.MANUAL_REVIEW),
            _record("core-owned", PluginResourceCleanupStrategy.FORBID_DELETE),
        ]
    )
    dry_run = build_uninstall_dry_run(plugin_id="feedback", ledger=ledger)

    validation = validate_uninstall_dry_run(
        dry_run,
        plugin_id="feedback",
        ledger=ledger,
        confirmed=True,
    )

    assert validation.allowed is False
    assert "dry_run_contains_forbidden_delete_resources" in validation.blockers
    assert "dry_run_contains_manual_review_resources" in validation.blockers


def test_uninstall_dry_run_validation_requires_confirmation_for_delete() -> None:
    ledger = PluginResourceLedger([_record("delete-me", PluginResourceCleanupStrategy.DELETE)])
    dry_run = build_uninstall_dry_run(plugin_id="feedback", ledger=ledger)

    unconfirmed = validate_uninstall_dry_run(dry_run, plugin_id="feedback", ledger=ledger)
    confirmed = validate_uninstall_dry_run(
        dry_run,
        plugin_id="feedback",
        ledger=ledger,
        confirmed=True,
    )

    assert unconfirmed.allowed is False
    assert "dry_run_requires_confirmation" in unconfirmed.blockers
    assert confirmed.allowed is True
    assert confirmed.blockers == []
