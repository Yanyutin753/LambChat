"""Pydantic response models for Plugin Runtime routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PluginRuntimeIssueResponse(BaseModel):
    plugin_id: str
    code: str
    message: str
    phase: str


class PluginRuntimeRouteResponse(BaseModel):
    name: str
    prefix: str
    module: str
    required_permissions: list[str]
    tags: list[str]


class PluginRuntimeToolResponse(BaseModel):
    name: str
    module: str
    required_permissions: list[str]
    legacy_ids: list[str]


class PluginRuntimeEffectResponse(BaseModel):
    action: str
    effect: str


class PluginRuntimeAgentResponse(BaseModel):
    id: str
    module: str
    name: str
    description: str
    icon: str
    sort_order: int
    category: str | None = None
    required_permissions: list[str]


class PluginRuntimeMessageActionResponse(BaseModel):
    id: str
    target: str
    renderer: str
    order: int
    permissions: list[str]
    visible_when: dict[str, Any] | None = None


class PluginRuntimeFrontendResponse(BaseModel):
    routes: list[str]
    panels: list[str]
    nav_items: list[str]
    app_tabs: list[dict[str, Any]]
    app_panels: list[dict[str, Any]]
    sidebar_items: list[dict[str, Any]]
    user_menu_items: list[dict[str, Any]]
    tool_renderers: list[dict[str, Any]]
    file_viewers: list[dict[str, Any]]
    upload_handlers: list[dict[str, Any]]
    skill_importers: list[dict[str, Any]]
    channel_connectors: list[dict[str, Any]]
    message_actions: list[PluginRuntimeMessageActionResponse]
    chat_input_options: list[dict[str, Any]]
    chat_input_panels: list[dict[str, Any]]
    mention_providers: list[dict[str, Any]]
    welcome_surfaces: list[dict[str, Any]]
    assistant_identity_resolvers: list[dict[str, Any]]
    agent_categories: list[dict[str, Any]]
    project_options: list[dict[str, Any]]
    session_options: list[dict[str, Any]]
    channel_options: list[dict[str, Any]]
    scheduled_task_options: list[dict[str, Any]]
    settings_sections: list[str]
    i18n_namespaces: list[str]
    required_permissions: list[str]


class PluginRuntimeSideEffectResponse(BaseModel):
    action: str
    status: str
    message: str


class PluginRuntimePackageResponse(BaseModel):
    source_type: str
    manifest_authority: str
    static_fallback_used: bool
    static_fallback_fields: list[str]
    source_path: str | None
    manifest_path: str | None
    data_dir: str | None
    validated_at: str | None
    errors: list[str]
    layout: dict[str, Any]
    frontend_assets: dict[str, Any] | None = None
    data_template: dict[str, Any]
    data_policy: dict[str, Any]


class PluginRuntimePluginResponse(BaseModel):
    plugin_id: str
    name: str | None
    version: str | None
    api_version: str | None
    status: str
    state_source: str
    state_updated_at: datetime | None
    state_updated_by: str | None
    enabled: bool
    executable: bool
    core: bool
    install_type: str
    uninstallable: bool
    depends_on: list[str]
    permissions: list[str]
    routes: list[PluginRuntimeRouteResponse]
    agents: list[PluginRuntimeAgentResponse]
    tools: list[PluginRuntimeToolResponse]
    runtime_effects: list[PluginRuntimeEffectResponse]
    frontend: PluginRuntimeFrontendResponse
    resource_count: int
    resource_types: dict[str, int]
    dry_run_actions: dict[str, int]
    runtime_side_effect: PluginRuntimeSideEffectResponse
    package: PluginRuntimePackageResponse
    issues: list[PluginRuntimeIssueResponse]


class PluginRuntimeListResponse(BaseModel):
    plugins: list[PluginRuntimePluginResponse]
    total: int
    runtime: dict[str, Any]


class PluginRuntimeContributionStateResponse(BaseModel):
    plugin_id: str
    enabled: bool
    executable: bool
    status: str
    agents: list[PluginRuntimeAgentResponse] = []
    tools: list[PluginRuntimeToolResponse] = []
    frontend: PluginRuntimeFrontendResponse | None = None


class PluginRuntimeContributionStatesResponse(BaseModel):
    plugins: list[PluginRuntimeContributionStateResponse]
    total: int


class PluginRuntimeGuardSurfaceResponse(BaseModel):
    id: str
    label: str
    status: str
    enforced: bool
    failure_mode: str
    evidence: str


class PluginRuntimeAcceptanceRequirementResponse(BaseModel):
    section: str
    requirement_id: str
    description: str
    passed: bool
    evidence_refs: list[str]


class PluginRuntimeAcceptanceMatrixResponse(BaseModel):
    passed: bool
    total: int
    passed_count: int
    missing: list[str]
    sections: dict[str, int]
    requirements: list[PluginRuntimeAcceptanceRequirementResponse]


class PluginRuntimePhaseProgressResponse(BaseModel):
    phase: str
    title: str
    status: str
    passed: bool
    evidence: str


class PluginRuntimeFeedbackGateResponse(BaseModel):
    gate_id: str
    category: str
    passed: bool
    evidence: str


class PluginRuntimeFeedbackMigrationResponse(BaseModel):
    plugin_id: str
    ready_for_first_migration_step: bool
    satisfied_gates: list[str]
    missing_gates: list[str]
    gate_evidence: list[PluginRuntimeFeedbackGateResponse]
    risks: list[str]
    compatibility_notes: list[str]


class PluginRuntimeAuditRecordResponse(BaseModel):
    plugin_id: str
    action: str
    previous_status: str | None
    next_status: str
    actor_user_id: str | None
    actor_username: str | None
    reason: str | None
    created_at: datetime


class PluginRuntimeAuditResponse(BaseModel):
    plugin_id: str
    audit: list[PluginRuntimeAuditRecordResponse]
    total: int


class PluginSettingResponse(BaseModel):
    key: str
    qualified_key: str
    value: Any
    type: str
    label: str
    description: str
    group: str
    order: int
    default_value: Any
    sensitive: bool
    required: bool
    requires_restart: bool
    scope: str
    source: str
    updated_at: datetime | None
    updated_by: str | None
    legacy_system_setting_keys: list[str]
    options: list[str] | None = None
    json_schema: dict[str, Any] | None = None
    visible_when: dict[str, Any] | None = None


class PluginSettingGroupResponse(BaseModel):
    group: str
    count: int


class PluginSettingsResponse(BaseModel):
    plugin_id: str
    plugin_status: str
    plugin_executable: bool
    settings: list[PluginSettingResponse]
    groups: list[PluginSettingGroupResponse]
    migration_status: dict[str, Any]


class PluginSettingUpdate(BaseModel):
    value: Any


class PluginExportResponse(BaseModel):
    schema_version: str
    exported_at: datetime
    plugin_id: str
    install_type: str
    uninstallable: bool
    manifest: dict[str, Any] | None
    runtime_state: dict[str, Any]
    settings: list[dict[str, Any]]
    resources: dict[str, Any]
    dry_run: dict[str, Any]
    notes: list[str]


class PluginImportRequest(BaseModel):
    payload: dict[str, Any]
    import_settings: bool = True
    restore_state: bool = False


class PluginImportResponse(BaseModel):
    plugin_id: str
    status: str
    imported_settings: list[str]
    skipped_settings: list[str]
    warnings: list[str]


class PluginUninstallRequest(BaseModel):
    snapshot_id: str
    confirmed: bool = False
    reason: str | None = None


class PluginUninstallResponse(BaseModel):
    plugin_id: str
    status: str
    previous_status: str
    snapshot_id: str
    actions: dict[str, int]
    archived_resources: int
    kept_resources: int
    deleted_resources: int
    package_action: str
    package_archive_path: str | None
    plugin_data_retained: bool
    plugin_data_dir: str | None
    package_integrity: dict[str, Any] | None
    warnings: list[str]
    audit_action: str


class PluginResourceRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plugin_id: str
    resource_id: str
    resource_type: str
    scope: str
    owner_user_id: str | None
    owner_role: str | None
    created_by_plugin_version: str | None
    retention_policy: str
    cleanup_strategy: str
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime
    metadata: dict[str, str]


class PluginResourcesResponse(BaseModel):
    plugin_id: str
    resources: list[PluginResourceRecordResponse]
    total: int
    resource_types: dict[str, int]


class PluginDryRunResourceResponse(BaseModel):
    plugin_id: str
    resource_id: str
    resource_type: str
    action: str
    retention_policy: str
    cleanup_strategy: str
    scope: str
    requires_confirmation: bool
    irreversible: bool
    reason: str
    metadata: dict[str, str]


class PluginUninstallPackageDataPolicyResponse(BaseModel):
    package_folder_action: str | None
    plugin_data_folder_action: str | None
    plugin_data_config_action: str | None
    plugin_data_storage_action: str | None
    frontend_asset_action: str | None
    runtime_data_delete_allowed: bool
    sensitive_settings_delete_allowed: bool
    requires_physical_data_delete_confirmation: bool
    default_retention: str
    protected_resource_types: list[str]
    notes: list[str]


class PluginUninstallDryRunResponse(BaseModel):
    plugin_id: str
    created_at: datetime
    expires_at: datetime
    snapshot_id: str
    resource_fingerprint: str
    resource_count: int
    resources: list[PluginDryRunResourceResponse]
    actions: dict[str, int]
    warnings: list[str]
    requires_confirmation: list[str]
    rollback_notes: list[str]
    package_data_policy: PluginUninstallPackageDataPolicyResponse
    validation: dict[str, Any]


class PluginPackageDescriptorResponse(BaseModel):
    plugin_id: str
    source_type: str
    folder: str
    manifest_path: str
    data_dir: str
    validated_at: datetime
    valid: bool
    errors: list[str]
    layout: dict[str, Any]


class PluginPackagesResponse(BaseModel):
    plugin_root: str | None
    data_root: str | None
    packages: list[PluginPackageDescriptorResponse]
    errors: list[str]
    total: int


class PluginPackageImportRequest(BaseModel):
    source_path: str
    dry_run: bool = True


class PluginPackageImportResponse(BaseModel):
    plugin_id: str
    status: str
    dry_run: bool
    source_path: str
    target_path: str
    data_dir: str
    descriptor: PluginPackageDescriptorResponse
    integrity: dict[str, Any]
    actions: list[str]
    warnings: list[str]


class ArchivedPluginPackageResponse(BaseModel):
    archive_id: str
    plugin_id: str
    archive_path: str
    manifest_path: str
    data_dir: str
    archived_at: datetime | None
    integrity: dict[str, Any]
    valid: bool
    errors: list[str]


class ArchivedPluginPackagesResponse(BaseModel):
    plugin_root: str | None
    data_root: str | None
    archived: list[ArchivedPluginPackageResponse]
    total: int


class PluginPackageRestoreResponse(BaseModel):
    plugin_id: str
    archive_id: str
    status: str
    archive_path: str
    target_path: str
    data_dir: str
    integrity: dict[str, Any]
    warnings: list[str]


class PluginPackageExportResponse(BaseModel):
    schema_version: str
    exported_at: datetime
    plugin_id: str
    source_type: str
    source_path: str | None
    manifest_path: str | None
    data_dir: str | None
    package_summary: dict[str, Any]
    manifest: dict[str, Any] | None
    resources: dict[str, Any]
    data_snapshot: dict[str, Any]
    notes: list[str]


class PluginDataResponse(BaseModel):
    plugin_id: str
    data_dir: str
    exists: bool
    subdirs: list[str]
    defaults_path: str
    current_path: str
    runtime_state_path: str
    file_count: int
    total_bytes: int
    backup_count: int
    last_backup_path: str | None


class PluginPackageReviewRequest(BaseModel):
    reason: str | None = None


class PluginPackageReviewResponse(BaseModel):
    plugin_id: str
    package_sha256: str
    reviewed_at: datetime | None
    reviewed_by: str | None
    reviewer_username: str | None
    reason: str | None
    active_for_current_package: bool
    integrity: dict[str, Any]
