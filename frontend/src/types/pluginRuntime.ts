export interface PluginRuntimeIssue {
  plugin_id: string;
  code: string;
  message: string;
  phase: string;
}

export interface PluginRuntimeRoute {
  name: string;
  prefix: string;
  module: string;
  required_permissions: string[];
  tags: string[];
}

export interface PluginRuntimeTool {
  name: string;
  module: string;
  required_permissions: string[];
  legacy_ids: string[];
}

export interface PluginRuntimeFrontend {
  routes: string[];
  panels: string[];
  nav_items: string[];
  tool_renderers: string[];
  file_viewers: string[];
  skill_importers: string[];
  channel_connectors: string[];
  message_actions: string[];
  settings_sections: string[];
  i18n_namespaces: string[];
  required_permissions: string[];
}

export interface PluginRuntimeSideEffect {
  action: string;
  status: string;
  message: string;
}

export interface PluginPackageLayout {
  has_backend: boolean;
  has_frontend: boolean;
  has_frontend_dist: boolean;
  has_config_schema: boolean;
  has_config_defaults: boolean;
  has_resources: boolean;
  has_data_template: boolean;
  has_readme: boolean;
  backend_files: string[];
  frontend_files: string[];
}

export interface PluginFrontendAssetBundle {
  plugin_id: string;
  asset_schema: string;
  slots: string[];
  assets: string[];
  phase: string;
}

export interface PluginRuntimePackage {
  source_type: string;
  manifest_authority: string;
  static_fallback_used: boolean;
  static_fallback_fields: string[];
  source_path: string | null;
  manifest_path: string | null;
  data_dir: string | null;
  validated_at: string | null;
  errors: string[];
  layout: PluginPackageLayout;
  frontend_assets?: PluginFrontendAssetBundle | null;
  data_template: PluginDataTemplateSummary;
  data_policy: PluginPackageDataPolicy;
}

export interface PluginDataTemplateSummary {
  exists: boolean;
  file_count: number;
  total_bytes: number;
  files: string[];
}

export interface PluginPackageDataPolicy {
  runtime_data_in_archive: boolean;
  snapshot_metadata_in_export: boolean;
  default_retention: string;
  data_dir: string | null;
  sensitive_settings_included: boolean;
  notes: string[];
}

export interface PluginPackageIntegrity {
  algorithm: string;
  package_sha256: string;
  file_count: number;
  total_bytes: number;
  signed: boolean;
  signature_status: string;
  signature_path: string | null;
  notes: string[];
}

export interface PluginRuntimePlugin {
  plugin_id: string;
  name: string | null;
  version: string | null;
  api_version: string | null;
  status: string;
  state_source: string;
  state_updated_at: string | null;
  state_updated_by: string | null;
  enabled: boolean;
  executable: boolean;
  core: boolean;
  install_type: string;
  uninstallable: boolean;
  depends_on: string[];
  permissions: string[];
  routes: PluginRuntimeRoute[];
  tools: PluginRuntimeTool[];
  frontend: PluginRuntimeFrontend;
  resource_count: number;
  resource_types: Record<string, number>;
  dry_run_actions: Record<string, number>;
  runtime_side_effect: PluginRuntimeSideEffect;
  package?: PluginRuntimePackage;
  issues: PluginRuntimeIssue[];
}

export interface PluginPackageDescriptor {
  plugin_id: string;
  source_type: string;
  folder: string;
  manifest_path: string;
  data_dir: string;
  validated_at: string;
  valid: boolean;
  errors: string[];
  layout: PluginPackageLayout;
}

export interface PluginPackagesResponse {
  plugin_root: string | null;
  data_root: string | null;
  packages: PluginPackageDescriptor[];
  errors: string[];
  total: number;
}

export interface PluginPackageExportResponse {
  schema_version: string;
  exported_at: string;
  plugin_id: string;
  source_type: string;
  source_path: string | null;
  manifest_path: string | null;
  data_dir: string | null;
  package_summary: {
    layout: Partial<PluginPackageLayout>;
    config_defaults: Record<string, unknown>;
    frontend_assets?: PluginFrontendAssetBundle | null;
    data_template: PluginDataTemplateSummary;
    data_policy: PluginPackageDataPolicy;
    integrity?: PluginPackageIntegrity | null;
    standard_files: Record<string, boolean>;
    file_count: number;
    total_bytes: number;
    top_level_entries: string[];
  };
  manifest: Record<string, unknown> | null;
  resources: Record<string, unknown>;
  data_snapshot: Record<string, unknown>;
  notes: string[];
}

export interface PluginPackageImportResponse {
  plugin_id: string;
  status: string;
  dry_run: boolean;
  source_path: string;
  target_path: string;
  data_dir: string;
  descriptor: PluginPackageDescriptor;
  integrity: PluginPackageIntegrity;
  actions: string[];
  warnings: string[];
}

export interface ArchivedPluginPackage {
  archive_id: string;
  plugin_id: string;
  archive_path: string;
  manifest_path: string;
  data_dir: string;
  integrity: PluginPackageIntegrity;
  archived_at: string | null;
  valid: boolean;
  errors: string[];
}

export interface ArchivedPluginPackagesResponse {
  plugin_root: string | null;
  data_root: string | null;
  archived: ArchivedPluginPackage[];
  total: number;
}

export interface PluginPackageRestoreResponse {
  plugin_id: string;
  archive_id: string;
  status: string;
  archive_path: string;
  target_path: string;
  data_dir: string;
  integrity: PluginPackageIntegrity;
  warnings: string[];
}

export interface PluginPackageReviewResponse {
  plugin_id: string;
  package_sha256: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  reviewer_username: string | null;
  reason: string | null;
  active_for_current_package: boolean;
  integrity: PluginPackageIntegrity;
}

export interface PluginDataResponse {
  plugin_id: string;
  data_dir: string;
  exists: boolean;
  subdirs: string[];
  defaults_path: string;
  current_path: string;
  runtime_state_path: string;
  file_count: number;
  total_bytes: number;
  backup_count: number;
  last_backup_path: string | null;
}

export interface PluginRuntimeAuditRecord {
  plugin_id: string;
  action: string;
  previous_status: string | null;
  next_status: string;
  actor_user_id: string | null;
  actor_username: string | null;
  reason: string | null;
  created_at: string;
}

export interface PluginRuntimeAuditResponse {
  plugin_id: string;
  audit: PluginRuntimeAuditRecord[];
  total: number;
}

export interface PluginSettingItem {
  key: string;
  qualified_key: string;
  value: unknown;
  type: "string" | "text" | "number" | "boolean" | "select" | "json" | string;
  label: string;
  description: string;
  group: string;
  order: number;
  default_value: unknown;
  sensitive: boolean;
  required: boolean;
  requires_restart: boolean;
  scope: string;
  source: string;
  updated_at: string | null;
  updated_by: string | null;
  legacy_system_setting_keys: string[];
  options?: string[] | null;
  json_schema?: Record<string, unknown> | null;
  visible_when?: Record<string, unknown> | null;
}

export interface PluginSettingsResponse {
  plugin_id: string;
  plugin_status: string;
  plugin_executable: boolean;
  settings: PluginSettingItem[];
  groups: Array<{ group: string; count: number }>;
  migration_status: Record<string, unknown>;
}

export interface PluginRuntimeListResponse {
  plugins: PluginRuntimePlugin[];
  total: number;
  runtime: {
    api_versions: string[];
    mode: string;
    supports_hot_install: boolean;
    supports_remote_packages: boolean;
    supports_local_folder_packages: boolean;
    supports_plugin_data_dir: boolean;
    supports_package_integrity: boolean;
    requires_signed_user_installed_enable: boolean;
    supports_physical_uninstall: boolean;
    supports_uninstall_dry_run_validation: boolean;
    supports_remote_package_import: boolean;
    supports_state_persistence: boolean;
    supports_audit: boolean;
    guard_surfaces: Array<{
      id: string;
      label: string;
      status: string;
      enforced: boolean;
      failure_mode: string;
      evidence: string;
    }>;
    phase_progress: Array<{
      phase: string;
      title: string;
      status: string;
      passed: boolean;
      evidence: string;
    }>;
    feedback_migration: {
      plugin_id: string;
      ready_for_first_migration_step: boolean;
      satisfied_gates: string[];
      missing_gates: string[];
      gate_evidence: Array<{
        gate_id: string;
        category: string;
        passed: boolean;
        evidence: string;
      }>;
      risks: string[];
      compatibility_notes: string[];
    };
    acceptance_matrix: {
      passed: boolean;
      total: number;
      passed_count: number;
      missing: string[];
      sections: Record<string, number>;
      requirements: Array<{
        section: string;
        requirement_id: string;
        description: string;
        passed: boolean;
        evidence_refs: string[];
      }>;
    };
  };
}

export interface PluginExportResponse {
  schema_version: string;
  exported_at: string;
  plugin_id: string;
  install_type: string;
  uninstallable: boolean;
  manifest: Record<string, unknown> | null;
  runtime_state: Record<string, unknown>;
  settings: Array<Record<string, unknown>>;
  resources: Record<string, unknown>;
  dry_run: Record<string, unknown>;
  notes: string[];
}

export interface PluginImportResponse {
  plugin_id: string;
  status: string;
  imported_settings: string[];
  skipped_settings: string[];
  warnings: string[];
}

export interface PluginUninstallResponse {
  plugin_id: string;
  status: string;
  previous_status: string;
  snapshot_id: string;
  actions: Record<string, number>;
  archived_resources: number;
  kept_resources: number;
  deleted_resources: number;
  package_action: string;
  package_archive_path: string | null;
  plugin_data_retained: boolean;
  plugin_data_dir: string | null;
  package_integrity: PluginPackageIntegrity | null;
  warnings: string[];
  audit_action: string;
}

export interface PluginRuntimeContributionState {
  plugin_id: string;
  enabled: boolean;
  executable: boolean;
  status: string;
}

export interface PluginRuntimeContributionStatesResponse {
  plugins: PluginRuntimeContributionState[];
  total: number;
}

export interface PluginResourceRecord {
  plugin_id: string;
  resource_id: string;
  resource_type: string;
  scope: string;
  owner_user_id: string | null;
  owner_role: string | null;
  created_by_plugin_version: string | null;
  retention_policy: string;
  cleanup_strategy: string;
  created_at: string;
  updated_at: string;
  last_seen_at: string;
  metadata: Record<string, string>;
}

export interface PluginResourcesResponse {
  plugin_id: string;
  resources: PluginResourceRecord[];
  total: number;
  resource_types: Record<string, number>;
}

export interface PluginDryRunResource {
  plugin_id: string;
  resource_id: string;
  resource_type: string;
  action: string;
  retention_policy: string;
  cleanup_strategy: string;
  scope: string;
  requires_confirmation: boolean;
  irreversible: boolean;
  reason: string;
  metadata: Record<string, string>;
}

export interface PluginUninstallPackageDataPolicy {
  package_folder_action: string | null;
  plugin_data_folder_action: string | null;
  plugin_data_config_action: string | null;
  plugin_data_storage_action: string | null;
  frontend_asset_action: string | null;
  runtime_data_delete_allowed: boolean;
  sensitive_settings_delete_allowed: boolean;
  requires_physical_data_delete_confirmation: boolean;
  default_retention: string;
  protected_resource_types: string[];
  notes: string[];
}

export interface PluginUninstallDryRunResponse {
  plugin_id: string;
  created_at: string;
  expires_at: string;
  snapshot_id: string;
  resource_fingerprint: string;
  resource_count: number;
  resources: PluginDryRunResource[];
  actions: Record<string, number>;
  warnings: string[];
  requires_confirmation: string[];
  rollback_notes: string[];
  package_data_policy: PluginUninstallPackageDataPolicy;
  validation: {
    allowed: boolean;
    expired: boolean;
    resource_changed: boolean;
    blockers: string[];
    warnings: string[];
    checked_at: string;
    supports_physical_uninstall: boolean;
  };
}
