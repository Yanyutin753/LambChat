"""Plugin resource ownership ledger primitives."""

from __future__ import annotations

from builtins import list as builtin_list
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum


class PluginResourceType(str, Enum):
    BACKEND_ROUTE = "backend_route"
    FRONTEND_ROUTE = "frontend_route"
    PANEL = "panel"
    NAV_ITEM = "nav_item"
    APP_TAB = "app_tab"
    APP_PANEL = "app_panel"
    SIDEBAR_ITEM = "sidebar_item"
    USER_MENU_ITEM = "user_menu_item"
    AGENT = "agent"
    TOOL = "tool"
    TOOL_RENDERER = "tool_renderer"
    FILE_VIEWER = "file_viewer"
    UPLOAD_HANDLER = "upload_handler"
    SKILL_IMPORTER = "skill_importer"
    PERMISSION = "permission"
    SETTING = "setting"
    ENV_KEY_DECLARATION = "env_key_declaration"
    SCHEDULER_JOB = "scheduler_job"
    LISTENER = "listener"
    MIGRATION = "migration"
    DB_DOCUMENT = "db_document"
    DB_COLLECTION = "db_collection"
    DB_INDEX = "db_index"
    FILE = "file"
    CACHE_KEY = "cache_key"
    I18N_NAMESPACE = "i18n_namespace"
    NOTIFICATION_CHANNEL = "notification_channel"
    APPROVAL_SCENARIO = "approval_scenario"
    USAGE_REPORT = "usage_report"
    SHARE_TARGET = "share_target"
    CHANNEL_CONNECTOR = "channel_connector"
    MESSAGE_ACTION = "message_action"
    CHAT_INPUT_OPTION = "chat_input_option"
    CHAT_INPUT_PANEL = "chat_input_panel"
    MENTION_PROVIDER = "mention_provider"
    WELCOME_SURFACE = "welcome_surface"
    ASSISTANT_IDENTITY_RESOLVER = "assistant_identity_resolver"
    AGENT_CATEGORY = "agent_category"
    PROJECT_OPTION = "project_option"
    SESSION_OPTION = "session_option"
    CHANNEL_OPTION = "channel_option"
    SCHEDULED_TASK_OPTION = "scheduled_task_option"
    PLUGIN_PACKAGE_FOLDER = "plugin_package_folder"
    PLUGIN_DATA_FOLDER = "plugin_data_folder"
    PLUGIN_DATA_CONFIG = "plugin_data_config"
    PLUGIN_DATA_STORAGE = "plugin_data_storage"
    PLUGIN_FRONTEND_ASSET = "plugin_frontend_asset"
    PLUGIN_MIGRATION_SCRIPT = "plugin_migration_script"


class PluginResourceScope(str, Enum):
    GLOBAL = "global"
    USER = "user"
    ROLE = "role"
    PROJECT = "project"
    SESSION = "session"
    CHANNEL = "channel"
    SCHEDULED_TASK = "scheduled_task"
    SYSTEM = "system"


class PluginResourceRetentionPolicy(str, Enum):
    DELETE_ON_UNINSTALL = "delete_on_uninstall"
    KEEP_USER_DATA = "keep_user_data"
    ARCHIVE_METADATA = "archive_metadata"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    CORE_OWNED_DO_NOT_DELETE = "core_owned_do_not_delete"


class PluginResourceCleanupStrategy(str, Enum):
    DELETE = "delete"
    KEEP = "keep"
    ARCHIVE = "archive"
    MANUAL_REVIEW = "manual_review"
    FORBID_DELETE = "forbid_delete"


@dataclass(frozen=True)
class PluginResourceRecord:
    """One plugin-owned or plugin-declared resource."""

    plugin_id: str
    resource_id: str
    resource_type: PluginResourceType
    scope: PluginResourceScope = PluginResourceScope.GLOBAL
    owner_user_id: str | None = None
    owner_role: str | None = None
    created_by_plugin_version: str | None = None
    retention_policy: PluginResourceRetentionPolicy = PluginResourceRetentionPolicy.KEEP_USER_DATA
    cleanup_strategy: PluginResourceCleanupStrategy = PluginResourceCleanupStrategy.KEEP
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, PluginResourceType, str]:
        return (self.plugin_id, self.resource_type, self.resource_id)

    def mark_seen(self, when: datetime | None = None) -> "PluginResourceRecord":
        now = when or datetime.now(UTC)
        return replace(self, updated_at=now, last_seen_at=now)


class PluginResourceConflictError(ValueError):
    """Raised when another plugin already owns a resource id/type pair."""


class PluginResourceLedger:
    """In-memory resource ledger used by the static plugin runtime phase."""

    def __init__(self, records: Iterable[PluginResourceRecord] | None = None) -> None:
        self._records: dict[tuple[str, PluginResourceType, str], PluginResourceRecord] = {}
        self._ownership_index: dict[tuple[PluginResourceType, str], str] = {}
        if records:
            for record in records:
                self.register(record)

    def register(self, record: PluginResourceRecord) -> PluginResourceRecord:
        owner_key = (record.resource_type, record.resource_id)
        shared_declaration = record.resource_type is PluginResourceType.PERMISSION
        if not shared_declaration:
            existing_owner = self._ownership_index.get(owner_key)
            if existing_owner is not None and existing_owner != record.plugin_id:
                raise PluginResourceConflictError(
                    f"resource {record.resource_type.value}:{record.resource_id} "
                    f"already belongs to plugin {existing_owner}"
                )

        existing = self._records.get(record.key)
        stored = record if existing is None else record.mark_seen()
        self._records[record.key] = stored
        if not shared_declaration:
            self._ownership_index[owner_key] = record.plugin_id
        return stored

    def list(
        self,
        *,
        plugin_id: str | None = None,
        resource_type: PluginResourceType | str | None = None,
        scope: PluginResourceScope | str | None = None,
    ) -> builtin_list[PluginResourceRecord]:
        records = builtin_list(self._records.values())
        if plugin_id is not None:
            records = [record for record in records if record.plugin_id == plugin_id]
        if resource_type is not None:
            expected_type = PluginResourceType(resource_type)
            records = [record for record in records if record.resource_type is expected_type]
        if scope is not None:
            expected_scope = PluginResourceScope(scope)
            records = [record for record in records if record.scope is expected_scope]
        return records

    def get(
        self,
        *,
        plugin_id: str,
        resource_type: PluginResourceType | str,
        resource_id: str,
    ) -> PluginResourceRecord | None:
        return self._records.get((plugin_id, PluginResourceType(resource_type), resource_id))

    def register_manifest_resources(
        self,
        *,
        plugin_id: str,
        plugin_version: str,
        backend_routes: Iterable[str] = (),
        frontend_routes: Iterable[str] = (),
        panels: Iterable[str] = (),
        nav_items: Iterable[str] = (),
        app_tabs: Iterable[str] = (),
        app_panels: Iterable[str] = (),
        sidebar_items: Iterable[str] = (),
        user_menu_items: Iterable[str] = (),
        agents: Iterable[str] = (),
        tools: Iterable[str] = (),
        tool_renderers: Iterable[str] = (),
        file_viewers: Iterable[str] = (),
        upload_handlers: Iterable[str] = (),
        skill_importers: Iterable[str] = (),
        channel_connectors: Iterable[str] = (),
        message_actions: Iterable[str] = (),
        chat_input_options: Iterable[str] = (),
        chat_input_panels: Iterable[str] = (),
        mention_providers: Iterable[str] = (),
        welcome_surfaces: Iterable[str] = (),
        assistant_identity_resolvers: Iterable[str] = (),
        agent_categories: Iterable[str] = (),
        project_options: Iterable[str] = (),
        session_options: Iterable[str] = (),
        channel_options: Iterable[str] = (),
        scheduled_task_options: Iterable[str] = (),
        permissions: Iterable[str] = (),
        settings: Iterable[str | tuple[str, str]] = (),
        env_keys: Iterable[str] = (),
        scheduler_jobs: Iterable[str] = (),
        event_listeners: Iterable[str] = (),
        migrations: Iterable[str] = (),
        i18n_namespaces: Iterable[str] = (),
        records: Iterable[PluginResourceRecord] = (),
    ) -> builtin_list[PluginResourceRecord]:
        registered: builtin_list[PluginResourceRecord] = []
        declarations = [
            (PluginResourceType.BACKEND_ROUTE, backend_routes, PluginResourceCleanupStrategy.KEEP),
            (
                PluginResourceType.FRONTEND_ROUTE,
                frontend_routes,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (PluginResourceType.PANEL, panels, PluginResourceCleanupStrategy.KEEP),
            (PluginResourceType.NAV_ITEM, nav_items, PluginResourceCleanupStrategy.KEEP),
            (PluginResourceType.APP_TAB, app_tabs, PluginResourceCleanupStrategy.KEEP),
            (PluginResourceType.APP_PANEL, app_panels, PluginResourceCleanupStrategy.KEEP),
            (PluginResourceType.SIDEBAR_ITEM, sidebar_items, PluginResourceCleanupStrategy.KEEP),
            (
                PluginResourceType.USER_MENU_ITEM,
                user_menu_items,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (PluginResourceType.AGENT, agents, PluginResourceCleanupStrategy.KEEP),
            (PluginResourceType.TOOL, tools, PluginResourceCleanupStrategy.KEEP),
            (PluginResourceType.TOOL_RENDERER, tool_renderers, PluginResourceCleanupStrategy.KEEP),
            (PluginResourceType.FILE_VIEWER, file_viewers, PluginResourceCleanupStrategy.KEEP),
            (
                PluginResourceType.UPLOAD_HANDLER,
                upload_handlers,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.SKILL_IMPORTER,
                skill_importers,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.CHANNEL_CONNECTOR,
                channel_connectors,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.MESSAGE_ACTION,
                message_actions,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.CHAT_INPUT_OPTION,
                chat_input_options,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.CHAT_INPUT_PANEL,
                chat_input_panels,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.MENTION_PROVIDER,
                mention_providers,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.WELCOME_SURFACE,
                welcome_surfaces,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.ASSISTANT_IDENTITY_RESOLVER,
                assistant_identity_resolvers,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.AGENT_CATEGORY,
                agent_categories,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.PROJECT_OPTION,
                project_options,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.SESSION_OPTION,
                session_options,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.CHANNEL_OPTION,
                channel_options,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (
                PluginResourceType.SCHEDULED_TASK_OPTION,
                scheduled_task_options,
                PluginResourceCleanupStrategy.KEEP,
            ),
            (PluginResourceType.PERMISSION, permissions, PluginResourceCleanupStrategy.ARCHIVE),
            (
                PluginResourceType.ENV_KEY_DECLARATION,
                env_keys,
                PluginResourceCleanupStrategy.ARCHIVE,
            ),
            (
                PluginResourceType.SCHEDULER_JOB,
                scheduler_jobs,
                PluginResourceCleanupStrategy.MANUAL_REVIEW,
            ),
            (
                PluginResourceType.LISTENER,
                event_listeners,
                PluginResourceCleanupStrategy.MANUAL_REVIEW,
            ),
            (PluginResourceType.MIGRATION, migrations, PluginResourceCleanupStrategy.ARCHIVE),
            (
                PluginResourceType.I18N_NAMESPACE,
                i18n_namespaces,
                PluginResourceCleanupStrategy.KEEP,
            ),
        ]
        for resource_type, resource_ids, cleanup_strategy in declarations:
            for resource_id in resource_ids:
                registered.append(
                    self.register(
                        PluginResourceRecord(
                            plugin_id=plugin_id,
                            resource_id=resource_id,
                            resource_type=resource_type,
                            created_by_plugin_version=plugin_version,
                            retention_policy=_retention_for_cleanup(cleanup_strategy),
                            cleanup_strategy=cleanup_strategy,
                        )
                    )
                )
        for record in records:
            registered.append(self.register(record))
        for setting in settings:
            resource_id, scope = _setting_resource_id_and_scope(setting)
            registered.append(
                self.register(
                    PluginResourceRecord(
                        plugin_id=plugin_id,
                        resource_id=resource_id,
                        resource_type=PluginResourceType.SETTING,
                        scope=scope,
                        created_by_plugin_version=plugin_version,
                        retention_policy=PluginResourceRetentionPolicy.ARCHIVE_METADATA,
                        cleanup_strategy=PluginResourceCleanupStrategy.ARCHIVE,
                    )
                )
            )
        return registered


def _setting_resource_id_and_scope(
    setting: str | tuple[str, str],
) -> tuple[str, PluginResourceScope]:
    if isinstance(setting, tuple):
        resource_id, scope = setting
        return resource_id, PluginResourceScope(scope)
    return setting, PluginResourceScope.GLOBAL


def _retention_for_cleanup(
    cleanup_strategy: PluginResourceCleanupStrategy,
) -> PluginResourceRetentionPolicy:
    if cleanup_strategy is PluginResourceCleanupStrategy.DELETE:
        return PluginResourceRetentionPolicy.DELETE_ON_UNINSTALL
    if cleanup_strategy is PluginResourceCleanupStrategy.ARCHIVE:
        return PluginResourceRetentionPolicy.ARCHIVE_METADATA
    if cleanup_strategy is PluginResourceCleanupStrategy.MANUAL_REVIEW:
        return PluginResourceRetentionPolicy.MANUAL_REVIEW_REQUIRED
    if cleanup_strategy is PluginResourceCleanupStrategy.FORBID_DELETE:
        return PluginResourceRetentionPolicy.CORE_OWNED_DO_NOT_DELETE
    return PluginResourceRetentionPolicy.KEEP_USER_DATA
