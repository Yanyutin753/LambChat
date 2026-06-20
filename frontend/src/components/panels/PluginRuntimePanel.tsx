import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Archive,
  Ban,
  Box,
  Check,
  ChevronDown,
  Database,
  Download,
  Eye,
  Flag,
  GitBranch,
  ListChecks,
  PauseCircle,
  Plug,
  PlayCircle,
  RefreshCw,
  RotateCw,
  ShieldCheck,
  Trash2,
  Upload,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, IconButton } from "../common";
import { EmptyState } from "../common/EmptyState";
import { PanelHeader } from "../common/PanelHeader";
import { useAuth } from "../../hooks/useAuth";
import { usePluginRuntime } from "../../hooks/usePluginRuntime";
import { buildPluginRuntimeImpactSummary } from "./pluginRuntimeImpactSummary";
import {
  legacyFrontendContributionCount,
  pluginContributionGroups,
  pluginContributionLabels,
  structuredFrontendContributionCount,
  type PluginContributionGroup,
} from "./pluginRuntimePanelUtils";
import {
  Permission,
  type ArchivedPluginPackage,
  type PluginRuntimeAuditResponse,
  type PluginDataResponse,
  type PluginPackageReviewResponse,
  type PluginUninstallDryRunResponse,
  type PluginRuntimePlugin,
  type PluginRuntimeListResponse,
  type PluginSettingsResponse,
} from "../../types";

interface PluginRuntimePanelProps {
  embedded?: boolean;
}

function countValues(values: Record<string, number>): number {
  return Object.values(values).reduce((sum, value) => sum + value, 0);
}

function formatCounts(values: Record<string, number>): string {
  const entries = Object.entries(values);
  if (entries.length === 0) return "0";
  return entries.map(([key, value]) => `${key}: ${value}`).join(" · ");
}

function PluginOwnershipOverview({ plugins }: { plugins: PluginRuntimePlugin[] }) {
  const { t } = useTranslation();
  const visiblePlugins = plugins.filter(
    (plugin) => pluginContributionLabels(plugin).length > 0,
  );

  if (visiblePlugins.length === 0) return null;

  return (
    <section className="mb-4 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-4 py-3 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-theme-text-secondary">
        <Eye size={15} />
        <span>{t("pluginRuntime.ownership.title")}</span>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {visiblePlugins.map((plugin) => {
          const labels = pluginContributionLabels(plugin);
          return (
            <div
              key={plugin.plugin_id}
              className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0 text-sm font-semibold text-theme-text">
                  {plugin.name || plugin.plugin_id}
                </div>
                <span className={statusClassName(plugin.status)}>{plugin.status}</span>
              </div>
              <div className="mt-1 text-[0.72rem] text-theme-text-secondary">
                {plugin.executable
                  ? t("pluginRuntime.ownership.active")
                  : t("pluginRuntime.ownership.blocked")}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {labels.slice(0, 10).map((label) => (
                  <span key={label} className="skill-meta-pill max-w-full truncate">
                    {label}
                  </span>
                ))}
                {labels.length > 10 && (
                  <span className="skill-meta-pill">
                    +{labels.length - 10}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function statusClassName(status: string): string {
  if (status === "enabled") return "skill-status-pill skill-status-pill--active";
  if (status === "disabled") return "skill-status-pill skill-status-pill--disabled";
  return "skill-status-pill tag-error";
}

function sideEffectStatusClassName(status: string): string {
  if (status === "succeeded" || status === "available") {
    return "skill-status-pill skill-status-pill--active";
  }
  if (status === "failed") return "skill-status-pill tag-error";
  return "skill-meta-pill";
}

function PluginMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2">
      <div className="text-[0.68rem] font-medium uppercase text-theme-text-secondary">
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-theme-text">{value}</div>
    </div>
  );
}

function MigrationProgressOverview({
  phases,
  feedbackMigration,
}: {
  phases?: PluginRuntimeListResponse["runtime"]["phase_progress"];
  feedbackMigration?: PluginRuntimeListResponse["runtime"]["feedback_migration"];
}) {
  const { t } = useTranslation();

  if (!phases || phases.length === 0) return null;

  const passedCount = phases.filter((phase) => phase.passed).length;

  return (
    <section className="mb-4 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-4 py-3 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase text-theme-text-secondary">
          <Flag size={15} />
          <span>{t("pluginRuntime.progress.title")}</span>
        </div>
        <span className="skill-status-pill skill-status-pill--active">
          {passedCount}/{phases.length}
        </span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {phases.map((phase) => (
          <div
            key={phase.phase}
            className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 text-sm font-semibold text-theme-text">
                {t(`pluginRuntime.progress.phases.${phase.phase}`, phase.title)}
              </div>
              <span
                className={
                  phase.passed
                    ? "skill-status-pill skill-status-pill--active"
                    : "skill-status-pill tag-error"
                }
              >
                {phase.passed
                  ? t("pluginRuntime.progress.passed")
                  : t("pluginRuntime.progress.missing")}
              </span>
            </div>
            <div className="mt-2 text-xs leading-relaxed text-theme-text-secondary">
              {t(`pluginRuntime.progress.evidence.${phase.phase}`, phase.evidence)}
            </div>
          </div>
        ))}
      </div>
      {feedbackMigration && (
        <div className="mt-4 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-3 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-semibold text-theme-text">
              {t("pluginRuntime.feedbackMigration.title")}
            </div>
            <span
              className={
                feedbackMigration.ready_for_first_migration_step
                  ? "skill-status-pill skill-status-pill--active"
                  : "skill-status-pill tag-error"
              }
            >
              {feedbackMigration.ready_for_first_migration_step
                ? t("pluginRuntime.feedbackMigration.ready")
                : t("pluginRuntime.feedbackMigration.blocked")}
            </span>
          </div>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <PluginMetric
              label={t("pluginRuntime.feedbackMigration.satisfied")}
              value={feedbackMigration.satisfied_gates.length}
            />
            <PluginMetric
              label={t("pluginRuntime.feedbackMigration.missing")}
              value={feedbackMigration.missing_gates.length}
            />
            <PluginMetric
              label={t("pluginRuntime.feedbackMigration.plugin")}
              value={feedbackMigration.plugin_id}
            />
          </div>
          <div className="mt-3 grid gap-2 lg:grid-cols-2">
            {feedbackMigration.gate_evidence.map((gate) => (
              <div
                key={gate.gate_id}
                className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-semibold text-theme-text">{gate.gate_id}</span>
                  <span
                    className={
                      gate.passed
                        ? "skill-status-pill skill-status-pill--active"
                        : "skill-status-pill tag-error"
                    }
                  >
                    {gate.passed
                      ? t("pluginRuntime.feedbackMigration.passed")
                      : t("pluginRuntime.feedbackMigration.failed")}
                  </span>
                </div>
                <div className="mt-1 text-[0.72rem] text-theme-text-secondary">
                  {gate.category}
                </div>
                <div className="mt-2 leading-relaxed text-theme-text-secondary">
                  {gate.evidence}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function GuardSurfaceMatrix({
  surfaces,
}: {
  surfaces: PluginRuntimeListResponse["runtime"]["guard_surfaces"];
}) {
  const { t } = useTranslation();

  if (!surfaces || surfaces.length === 0) return null;

  return (
    <section className="mb-4 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-4 py-3 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase text-theme-text-secondary">
        <ShieldCheck size={15} />
        <span>{t("pluginRuntime.guardMatrix.title")}</span>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {surfaces.map((surface) => (
          <div
            key={surface.id}
            className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 text-sm font-semibold text-theme-text">
                {t(`pluginRuntime.guardMatrix.surfaces.${surface.id}`, surface.label)}
              </div>
              <span
                className={
                  surface.status === "enforced"
                    ? "skill-status-pill skill-status-pill--active"
                    : surface.status === "blocked"
                      ? "skill-status-pill skill-status-pill--disabled"
                      : "skill-meta-pill"
                }
              >
                {surface.status}
              </span>
            </div>
            <div className="mt-1 text-[0.72rem] text-theme-text-secondary">
              {t("pluginRuntime.guardMatrix.failureMode")}: {surface.failure_mode}
            </div>
            <div className="mt-2 text-xs leading-relaxed text-theme-text-secondary">
              {surface.evidence}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function AcceptanceMatrixOverview({
  matrix,
}: {
  matrix?: PluginRuntimeListResponse["runtime"]["acceptance_matrix"];
}) {
  const { t } = useTranslation();

  if (!matrix) return null;

  const sectionLabels = Object.entries(matrix.sections).map(
    ([section, count]) => `${section}: ${count}`,
  );

  return (
    <section className="mb-4 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-4 py-3 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase text-theme-text-secondary">
          <ListChecks size={15} />
          <span>{t("pluginRuntime.acceptance.title")}</span>
        </div>
        <span
          className={
            matrix.passed
              ? "skill-status-pill skill-status-pill--active"
              : "skill-status-pill tag-error"
          }
        >
          {matrix.passed ? t("pluginRuntime.acceptance.passed") : t("pluginRuntime.acceptance.missing")}
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <PluginMetric
          label={t("pluginRuntime.acceptance.total")}
          value={matrix.total}
        />
        <PluginMetric
          label={t("pluginRuntime.acceptance.passedCount")}
          value={matrix.passed_count}
        />
        <PluginMetric
          label={t("pluginRuntime.acceptance.missingCount")}
          value={matrix.missing.length}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {sectionLabels.map((label) => (
          <span key={label} className="skill-meta-pill max-w-full truncate">
            {label}
          </span>
        ))}
      </div>
      {matrix.missing.length > 0 && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {matrix.missing.join(" / ")}
        </div>
      )}
    </section>
  );
}

function ContributionPreviewList({
  label,
  values,
}: {
  label: string;
  values: readonly string[];
}) {
  return (
    <div className="min-w-0 rounded-md bg-[var(--theme-bg)] px-3 py-2">
      <div className="text-[0.68rem] font-medium uppercase text-theme-text-secondary">
        {label}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {values.length > 0 ? (
          values.map((value) => (
            <span key={value} className="skill-meta-pill max-w-full truncate">
              {value}
            </span>
          ))
        ) : (
          <span className="text-xs text-theme-text-secondary">-</span>
        )}
      </div>
    </div>
  );
}

function settingDisplayValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2);
}

function parseSettingValue(type: string, value: string): unknown {
  if (type === "boolean") return value === "true";
  if (type === "number") return Number(value);
  if (type === "json") {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

function CompactStat({ label, value }: { label: string; value: string | number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-2 py-1 text-[0.7rem] text-theme-text-secondary">
      <span>{label}</span>
      <span className="font-semibold text-theme-text">{value}</span>
    </span>
  );
}

function PluginContributionGroupGrid({ groups }: { groups: PluginContributionGroup[] }) {
  if (groups.length === 0) {
    return (
      <div className="rounded-md bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
        No directory-declared contributions
      </div>
    );
  }

  return (
    <div className="grid gap-2 text-xs text-theme-text-secondary xl:grid-cols-2">
      {groups.map((group) => (
        <div key={group.id} className="rounded-md bg-[var(--theme-bg)] px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-medium text-theme-text">{group.title}</div>
            <span className="skill-status-pill skill-status-pill--active">
              {group.entries.length}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {group.entries.slice(0, 8).map((entry) => (
              <span key={entry} className="skill-meta-pill max-w-full truncate" title={entry}>
                {entry}
              </span>
            ))}
            {group.entries.length > 8 && (
              <span className="skill-meta-pill">+{group.entries.length - 8}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function PluginSettingsSection({
  plugin,
  settings,
  isSaving,
  onUpdateSetting,
}: {
  plugin: PluginRuntimePlugin;
  settings?: PluginSettingsResponse;
  isSaving: boolean;
  onUpdateSetting: (pluginId: string, key: string, value: unknown) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const items = settings?.settings ?? [];
  const settingsVersion = items
    .map((item) => `${item.key}:${settingDisplayValue(item.value)}:${item.updated_at ?? ""}`)
    .join("|");

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const item of items) {
      next[item.key] = settingDisplayValue(item.value);
    }
    setDrafts(next);
  }, [settings?.plugin_id, settingsVersion]);

  const groups = Array.from(new Set(items.map((item) => item.group || "general")));

  return (
    <section>
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-theme-text-secondary">
        <Box size={14} />
        <span>{t("pluginRuntime.settings.title")}</span>
      </div>
      <div className="rounded-md bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
        {!settings ? (
          <div>{t("common.loading")}</div>
        ) : items.length === 0 ? (
          <div>{t("pluginRuntime.settings.empty")}</div>
        ) : (
          <div className="space-y-3">
            {!plugin.executable && (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
                {t("pluginRuntime.settings.disabledHint")}
              </div>
            )}
            {groups.map((group) => (
              <div key={group} className="space-y-2">
                <div className="text-[0.68rem] font-semibold uppercase text-theme-text-secondary">
                  {group}
                </div>
                <div className="grid gap-2 xl:grid-cols-2">
                  {items
                    .filter((item) => (item.group || "general") === group)
                    .map((item) => {
                    const draft = drafts[item.key] ?? settingDisplayValue(item.value);
                    const label = item.label ? t(item.label, item.key) : item.key;
                    const description = item.description
                      ? t(item.description, item.description)
                      : item.qualified_key;
                    const changed = draft !== settingDisplayValue(item.value);
                    const inputClass = "mt-1 w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-2 py-1.5 text-xs text-theme-text outline-none focus:border-[var(--theme-accent)]";
                    return (
                      <div key={item.key} className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-3 py-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="min-w-0">
                            <div className="font-medium text-theme-text">{label}</div>
                            <div className="mt-0.5 truncate text-[0.72rem] text-theme-text-secondary" title={description}>
                              {description}
                            </div>
                          </div>
                          <span className="skill-meta-pill">{item.source}</span>
                        </div>
                        {item.type === "boolean" ? (
                          <select
                            className={inputClass}
                            value={draft === "true" ? "true" : "false"}
                            onChange={(event) =>
                              setDrafts((prev) => ({ ...prev, [item.key]: event.target.value }))
                            }
                          >
                            <option value="true">true</option>
                            <option value="false">false</option>
                          </select>
                        ) : item.type === "text" || item.type === "json" ? (
                          <textarea
                            className={`${inputClass} min-h-20 resize-y`}
                            value={draft}
                            onChange={(event) =>
                              setDrafts((prev) => ({ ...prev, [item.key]: event.target.value }))
                            }
                          />
                        ) : item.type === "select" && item.options ? (
                          <select
                            className={inputClass}
                            value={draft}
                            onChange={(event) =>
                              setDrafts((prev) => ({ ...prev, [item.key]: event.target.value }))
                            }
                          >
                            {item.options.map((option) => (
                              <option key={option} value={option}>{option}</option>
                            ))}
                          </select>
                        ) : (
                          <input
                            className={inputClass}
                            type={item.sensitive ? "password" : item.type === "number" ? "number" : "text"}
                            value={draft}
                            onChange={(event) =>
                              setDrafts((prev) => ({ ...prev, [item.key]: event.target.value }))
                            }
                          />
                        )}
                        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                          <div className="flex flex-wrap gap-1.5">
                            <span className="skill-meta-pill">{item.qualified_key}</span>
                            {item.sensitive && <span className="skill-meta-pill">secret</span>}
                          </div>
                          <Button
                            size="sm"
                            disabled={!changed || isSaving}
                            leftIcon={<Check size={12} />}
                            onClick={() => {
                              void onUpdateSetting(
                                plugin.plugin_id,
                                item.key,
                                parseSettingValue(item.type, draft),
                              );
                            }}
                          >
                            {t("common.save")}
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function PluginPackageSection({
  plugin,
  pluginData,
  packageReview,
  canManageRuntime,
  isChangingState,
  onReviewPackage,
  onResetPluginData,
}: {
  plugin: PluginRuntimePlugin;
  pluginData?: PluginDataResponse;
  packageReview?: PluginPackageReviewResponse;
  canManageRuntime: boolean;
  isChangingState: boolean;
  onReviewPackage: (pluginId: string) => void;
  onResetPluginData: (pluginId: string) => void;
}) {
  const packageInfo = plugin.package ?? {
    source_type: "static_manifest",
    manifest_authority: "static_manifest",
    static_fallback_used: false,
    static_fallback_fields: [],
    source_path: null,
    manifest_path: null,
    data_dir: null,
    validated_at: null,
    errors: [],
    frontend_assets: null,
    data_template: {
      exists: false,
      template: "plugin-data-template",
      file_count: 0,
      total_bytes: 0,
      files: [],
    },
    data_policy: {
      runtime_data_in_archive: false,
      snapshot_metadata_in_export: true,
      default_retention: "keep_user_data",
      data_dir: null,
      sensitive_settings_included: false,
      notes: [],
    },
    layout: {
      has_backend: false,
      has_frontend: false,
      has_frontend_dist: false,
      has_config_schema: false,
      has_config_defaults: false,
      has_resources: false,
      has_data_template: false,
      data_template: "plugin-data-template",
      has_readme: false,
      backend_files: [],
      frontend_files: [],
    },
  };
  const packageLayout = packageInfo.layout ?? {
    has_backend: false,
    has_frontend: false,
    has_frontend_dist: false,
    has_config_schema: false,
    has_config_defaults: false,
    has_resources: false,
    has_data_template: false,
    data_template: "plugin-data-template",
    has_readme: false,
    backend_files: [],
    frontend_files: [],
  };
  const hasErrors = packageInfo.errors.length > 0;
  const frontendAssets = packageInfo.frontend_assets;
  const dataTemplate = packageInfo.data_template ?? {
    exists: false,
    template: "plugin-data-template",
    file_count: 0,
    total_bytes: 0,
    files: [],
  };
  const dataPolicy = packageInfo.data_policy ?? {
    runtime_data_in_archive: false,
    snapshot_metadata_in_export: true,
    default_retention: "keep_user_data",
    data_dir: null,
    sensitive_settings_included: false,
    notes: [],
  };
  const dependencies = plugin.depends_on ?? [];
  const layoutItems = [
    ["backend/", packageLayout.has_backend],
    ["frontend/", packageLayout.has_frontend],
    ["frontend/dist/", packageLayout.has_frontend_dist],
    ["config/schema.json", packageLayout.has_config_schema],
    ["config/defaults.json", packageLayout.has_config_defaults],
    ["resources/resources.yaml", packageLayout.has_resources],
    [`${packageLayout.data_template || dataTemplate.template || "plugin-data-template"}/`, packageLayout.has_data_template],
    ["README", packageLayout.has_readme],
  ] as const;
  const requiredDataTemplateFiles = [
    "config/current.json",
    "config/defaults.json",
    "state/audit.jsonl",
  ];
  const integrity = packageReview?.integrity;
  const showReviewControls =
    canManageRuntime &&
    packageInfo.source_type === "installed" &&
    integrity?.signature_status === "unsigned";

  return (
    <section>
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-theme-text-secondary">
        <Box size={14} />
        <span>Package / Data</span>
      </div>
      <div className="space-y-2 text-xs text-theme-text-secondary">
        <div className="rounded-md bg-[var(--theme-bg)] px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-medium text-theme-text">{packageInfo.source_type}</div>
            <span className={hasErrors ? "skill-status-pill tag-error" : "skill-status-pill skill-status-pill--active"}>
              {hasErrors ? "package_error" : "validated"}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="skill-status-pill skill-status-pill--active">
              authority {packageInfo.manifest_authority ?? "static_manifest"}
            </span>
            <span className={packageInfo.static_fallback_used ? "skill-status-pill tag-error" : "skill-meta-pill"}>
              fallback {packageInfo.static_fallback_used ? "used" : "none"}
            </span>
            {(packageInfo.static_fallback_fields ?? []).map((field) => (
              <span key={field} className="skill-meta-pill">
                fallback {field}
              </span>
            ))}
          </div>
          <div className="mt-2 break-all">{packageInfo.source_path || "static manifest"}</div>
          {packageInfo.manifest_path && (
            <div className="mt-1 break-all">{packageInfo.manifest_path}</div>
          )}
          {integrity && (
            <div className="mt-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-2 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-theme-text">package review</div>
                <span className={packageReview?.active_for_current_package ? "skill-status-pill skill-status-pill--active" : "skill-meta-pill"}>
                  {packageReview?.active_for_current_package ? "reviewed" : "not reviewed"}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="skill-meta-pill">
                  sha256 {integrity.package_sha256.slice(0, 12)}
                </span>
                <span className="skill-meta-pill">
                  signature {integrity.signature_status}
                </span>
                <span className="skill-meta-pill">files {integrity.file_count}</span>
              </div>
              {packageReview?.reviewed_at && (
                <div className="mt-2 text-[0.72rem] text-theme-text-secondary">
                  {packageReview.reviewer_username || packageReview.reviewed_by || "reviewed"} · {new Date(packageReview.reviewed_at).toLocaleString()}
                </div>
              )}
              {showReviewControls && !packageReview?.active_for_current_package && (
                <div className="mt-2 flex justify-end">
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={isChangingState}
                    leftIcon={<ShieldCheck size={12} />}
                    onClick={() => onReviewPackage(plugin.plugin_id)}
                  >
                    Review hash
                  </Button>
                </div>
              )}
            </div>
          )}
          {packageInfo.validated_at && (
            <div className="mt-1">{new Date(packageInfo.validated_at).toLocaleString()}</div>
          )}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {layoutItems.map(([label, present]) => (
              <span
                key={label}
                className={present ? "skill-status-pill skill-status-pill--active" : "skill-meta-pill"}
              >
                {label}
              </span>
            ))}
          </div>
          <div className="mt-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-2 py-2">
            <div className="font-medium text-theme-text">dependencies</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {dependencies.length > 0 ? (
                dependencies.map((dependency) => (
                  <span key={dependency} className="skill-meta-pill">
                    {dependency}
                  </span>
                ))
              ) : (
                <span className="text-[0.72rem] text-theme-text-secondary">none</span>
              )}
            </div>
          </div>
          {(packageLayout.backend_files.length > 0 || packageLayout.frontend_files.length > 0) && (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-2 py-2">
                <div className="font-medium text-theme-text">backend</div>
                <div className="mt-1 break-words">
                  {packageLayout.backend_files.length > 0
                    ? packageLayout.backend_files.join(" / ")
                    : "-"}
                </div>
              </div>
              <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-2 py-2">
                <div className="font-medium text-theme-text">frontend</div>
                <div className="mt-1 break-words">
                  {packageLayout.frontend_files.length > 0
                    ? packageLayout.frontend_files.join(" / ")
                    : "-"}
                </div>
              </div>
            </div>
          )}
          {frontendAssets && (
            <div className="mt-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-2 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-theme-text">frontend assets</div>
                <span className="skill-status-pill skill-status-pill--active">
                  {frontendAssets.asset_schema}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {frontendAssets.slots.map((slot) => (
                  <span key={slot} className="skill-meta-pill">
                    slot {slot}
                  </span>
                ))}
                <span className="skill-meta-pill">
                  assets {frontendAssets.assets.length}
                </span>
                <span className="skill-meta-pill">
                  {frontendAssets.phase}
                </span>
              </div>
            </div>
          )}
          {dataTemplate.exists && (
            <div className="mt-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-2 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-medium text-theme-text">{dataTemplate.template}</div>
                <span className="skill-status-pill skill-status-pill--active">
                  files {dataTemplate.file_count}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <span className="skill-meta-pill">bytes {dataTemplate.total_bytes}</span>
                {requiredDataTemplateFiles.map((file) => (
                  <span
                    key={`required-${file}`}
                    className={
                      dataTemplate.files.includes(file)
                        ? "skill-meta-pill"
                        : "skill-meta-pill skill-meta-pill--muted"
                    }
                  >
                    {file}
                  </span>
                ))}
                {dataTemplate.files.slice(0, 6).map((file) => (
                  <span key={file} className="skill-meta-pill max-w-full truncate">
                    {file}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="mt-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-2 py-2">
            <div className="font-medium text-theme-text">data export policy</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="skill-meta-pill">
                archive runtime data {dataPolicy.runtime_data_in_archive ? "yes" : "no"}
              </span>
              <span className="skill-meta-pill">
                snapshot metadata {dataPolicy.snapshot_metadata_in_export ? "yes" : "no"}
              </span>
              <span className="skill-meta-pill">
                retention {dataPolicy.default_retention}
              </span>
              <span className="skill-meta-pill">
                sensitive settings {dataPolicy.sensitive_settings_included ? "included" : "excluded"}
              </span>
            </div>
          </div>
        </div>
        <div className="rounded-md bg-[var(--theme-bg)] px-3 py-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="font-medium text-theme-text">plugin-data</div>
            {canManageRuntime && (
              <Button
                size="sm"
                variant="secondary"
                loading={isChangingState}
                leftIcon={<RotateCw size={12} />}
                onClick={() => onResetPluginData(plugin.plugin_id)}
              >
                Reset data config
              </Button>
            )}
          </div>
          <div className="mt-2 break-all">{pluginData?.data_dir || packageInfo.data_dir || "-"}</div>
          {pluginData && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className="skill-meta-pill">files: {pluginData.file_count}</span>
              <span className="skill-meta-pill">bytes: {pluginData.total_bytes}</span>
              <span className="skill-meta-pill">subdirs: {pluginData.subdirs.length}</span>
              <span className="skill-meta-pill">backups: {pluginData.backup_count}</span>
            </div>
          )}
          {pluginData?.last_backup_path && (
            <div className="mt-2 truncate text-[0.72rem] text-theme-text-secondary" title={pluginData.last_backup_path}>
              last backup {pluginData.last_backup_path}
            </div>
          )}
        </div>
        {hasErrors && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
            {packageInfo.errors.join(" / ")}
          </div>
        )}
      </div>
    </section>
  );
}

function PluginCard({
  plugin,
  isExpanded,
  isLoadingDetails,
  resources,
  dryRun,
  audit,
  settings,
  pluginData,
  packageReview,
  runtimePlugins,
  canManageRuntime,
  isChangingState,
  onToggle,
  onSetEnabled,
  onUpdateSetting,
  onReviewPackage,
  onResetPluginData,
  onExportPlugin,
  onUninstallPlugin,
}: {
  plugin: PluginRuntimePlugin;
  isExpanded: boolean;
  isLoadingDetails: boolean;
  resources?: { total: number; resource_types: Record<string, number> };
  dryRun?: PluginUninstallDryRunResponse;
  audit?: PluginRuntimeAuditResponse;
  settings?: PluginSettingsResponse;
  pluginData?: PluginDataResponse;
  packageReview?: PluginPackageReviewResponse;
  runtimePlugins?: PluginRuntimeListResponse["plugins"];
  canManageRuntime: boolean;
  isChangingState: boolean;
  onToggle: () => void;
  onSetEnabled: (pluginId: string, enabled: boolean) => void;
  onUpdateSetting: (pluginId: string, key: string, value: unknown) => Promise<boolean>;
  onReviewPackage: (pluginId: string) => void;
  onResetPluginData: (pluginId: string) => void;
  onExportPlugin: (pluginId: string) => void;
  onUninstallPlugin: (pluginId: string) => void;
}) {
  const { t } = useTranslation();
  const impactSummary = buildPluginRuntimeImpactSummary(
    plugin,
    runtimePlugins,
  );
  const structuredFrontendCount = structuredFrontendContributionCount(plugin);
  const legacyFrontendCount = legacyFrontendContributionCount(plugin);
  const frontendContributionCount = structuredFrontendCount + legacyFrontendCount;
  const contributionCount =
    plugin.routes.length +
    plugin.agents.length +
    plugin.tools.length +
    frontendContributionCount;
  const dryRunTotal = countValues(plugin.dry_run_actions);
  const contributionGroups = pluginContributionGroups(plugin);
  const dependencies = plugin.depends_on ?? [];
  const settingsCount =
    settings?.settings.length ??
    plugin.resource_types.setting ??
    plugin.resource_types.settings ??
    plugin.resource_types.plugin_settings ??
    0;

  return (
    <article className="overflow-hidden rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm transition-shadow hover:shadow-md">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={isExpanded}
        className="flex w-full flex-col gap-2 px-3 py-2.5 text-left sm:flex-row sm:items-center sm:justify-between"
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex size-8 flex-shrink-0 items-center justify-center rounded-md bg-[var(--theme-bg-subtle)] text-theme-text-secondary ring-1 ring-[var(--theme-border)]">
            <Plug size={16} />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="max-w-[14rem] truncate text-sm font-semibold text-theme-text sm:max-w-[18rem]">
                {plugin.name || plugin.plugin_id}
              </h2>
              <span className={statusClassName(plugin.status)}>{plugin.status}</span>
              <span className="hidden text-[0.72rem] text-theme-text-secondary sm:inline">{plugin.plugin_id}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-[0.72rem] text-theme-text-secondary">
              <span>v{plugin.version || "-"}</span>
              <span>{plugin.api_version || "-"}</span>
              <span>{plugin.state_source}</span>
              <span>{t(`pluginRuntime.installTypes.${plugin.install_type}`, plugin.install_type)}</span>
              {plugin.state_updated_by && <span className="max-w-[7rem] truncate">{plugin.state_updated_by}</span>}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-theme-text-secondary sm:justify-end">
          <CompactStat label={t("pluginRuntime.metrics.settings")} value={settingsCount} />
          <CompactStat label={t("pluginRuntime.metrics.resources")} value={plugin.resource_count} />
          <CompactStat label={t("pluginRuntime.metrics.contributions")} value={contributionCount} />
          <CompactStat label="Deps" value={dependencies.length} />
          {canManageRuntime && (
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<Download size={14} />}
              onClick={(event) => {
                event.stopPropagation();
                onExportPlugin(plugin.plugin_id);
              }}
            >
              {t("pluginRuntime.actions.export")}
            </Button>
          )}
          {canManageRuntime && (
            <Button
              variant={plugin.enabled ? "danger" : "secondary"}
              size="sm"
              loading={isChangingState}
              leftIcon={
                plugin.enabled ? <PauseCircle size={14} /> : <PlayCircle size={14} />
              }
              onClick={(event) => {
                event.stopPropagation();
                onSetEnabled(plugin.plugin_id, !plugin.enabled);
              }}
            >
              {plugin.enabled
                ? t("pluginRuntime.actions.disable")
                : t("pluginRuntime.actions.enable")}
            </Button>
          )}
          {canManageRuntime && plugin.uninstallable && (
            <Button
              variant="danger"
              size="sm"
              loading={isChangingState}
              leftIcon={<Trash2 size={14} />}
              onClick={(event) => {
                event.stopPropagation();
                onUninstallPlugin(plugin.plugin_id);
              }}
            >
              {t("pluginRuntime.actions.uninstall")}
            </Button>
          )}
          <ChevronDown
            size={16}
            className={`ml-1 transition-transform ${isExpanded ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {isExpanded && (
        <div className="border-t border-[var(--theme-border)] px-3 pb-3 pt-2.5">
          <div className="mb-3 flex flex-wrap gap-1.5">
            <CompactStat label={t("pluginRuntime.metrics.routes")} value={plugin.routes.length} />
            <CompactStat label={t("pluginRuntime.metrics.frontend")} value={structuredFrontendCount} />
            {legacyFrontendCount > 0 && (
              <CompactStat label="Legacy UI" value={legacyFrontendCount} />
            )}
            <CompactStat label={t("pluginRuntime.metrics.dryRun")} value={dryRunTotal} />
            <CompactStat
              label={t("pluginRuntime.metrics.uninstall")}
              value={plugin.uninstallable ? t("common.yes", "Yes") : t("common.no", "No")}
            />
          </div>

          {!plugin.uninstallable && (
            <div className="mb-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-3 py-2 text-xs text-theme-text-secondary">
              {t("pluginRuntime.uninstall.protected")}
            </div>
          )}

          <div className="grid gap-3 lg:grid-cols-2">
            <section>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-theme-text-secondary">
                <GitBranch size={14} />
                <span>{t("pluginRuntime.contributions")}</span>
              </div>
              <PluginContributionGroupGrid groups={contributionGroups} />
            </section>

            <PluginSettingsSection
              plugin={plugin}
              settings={settings}
              onUpdateSetting={onUpdateSetting}
              isSaving={isLoadingDetails}
            />

            <PluginPackageSection
              plugin={plugin}
              pluginData={pluginData}
              packageReview={packageReview}
              canManageRuntime={canManageRuntime}
              isChangingState={isChangingState}
              onReviewPackage={onReviewPackage}
              onResetPluginData={onResetPluginData}
            />

            <section>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-theme-text-secondary">
                <ListChecks size={14} />
                <span>{t("pluginRuntime.contributionPreview.title")}</span>
              </div>
              <div className="space-y-2">
                <ContributionPreviewList
                  label={t("pluginRuntime.contributionPreview.active")}
                  values={impactSummary.activeEntries}
                />
                <ContributionPreviewList
                  label={t("pluginRuntime.contributionPreview.removedWhenDisabled")}
                  values={impactSummary.blockedWhenDisabled}
                />
                <ContributionPreviewList
                  label={t("pluginRuntime.contributionPreview.resources")}
                  values={impactSummary.resourceActions}
                />
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="flex items-center gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-3 py-2 text-xs text-theme-text-secondary">
                    <Ban size={14} className="flex-shrink-0" />
                    <span>{t("pluginRuntime.contributionPreview.disablePolicy")}</span>
                  </div>
                  <div className="flex items-center gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-3 py-2 text-xs text-theme-text-secondary">
                    <Archive size={14} className="flex-shrink-0" />
                    <span>{t("pluginRuntime.contributionPreview.uninstallPolicy")}</span>
                  </div>
                </div>
                <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2 font-semibold text-theme-text">
                      <RotateCw size={14} />
                      <span>{t("pluginRuntime.runtimeSideEffect.title")}</span>
                    </div>
                    <span className={sideEffectStatusClassName(plugin.runtime_side_effect.status)}>
                      {plugin.runtime_side_effect.status}
                    </span>
                  </div>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    <div>
                      <span className="font-medium text-theme-text">
                        {t("pluginRuntime.runtimeSideEffect.action")}:
                      </span>
                      <span>{plugin.runtime_side_effect.action}</span>
                    </div>
                    <div>
                      <span className="font-medium text-theme-text">
                        {t("pluginRuntime.runtimeSideEffect.status")}:
                      </span>
                      <span>{plugin.runtime_side_effect.status}</span>
                    </div>
                  </div>
                  <div className="mt-2 leading-relaxed">
                    {plugin.runtime_side_effect.message}
                  </div>
                </div>
              </div>
            </section>

            <section>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-theme-text-secondary">
                <Database size={14} />
                <span>{t("pluginRuntime.resources")}</span>
              </div>
              <div className="rounded-md bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
                <div className="font-medium text-theme-text">
                  {resources?.total ?? plugin.resource_count} {t("pluginRuntime.resourceEntries")}
                </div>
                <div className="mt-1 break-words">
                  {formatCounts(resources?.resource_types ?? plugin.resource_types)}
                </div>
              </div>
              <div className="mt-2 rounded-md bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
                <div className="font-medium text-theme-text">
                  {t("pluginRuntime.dryRun")}
                </div>
                <div className="mt-1 break-words">
                  {formatCounts(dryRun?.actions ?? plugin.dry_run_actions)}
                </div>
                {dryRun && (
                  <div className="mt-2 space-y-1 text-[0.72rem] leading-relaxed">
                    <div>
                      {t("pluginRuntime.dryRunSnapshot")}: {dryRun.snapshot_id.slice(0, 12)}
                    </div>
                    <div>
                      {t("pluginRuntime.dryRunExpires")}: {new Date(dryRun.expires_at).toLocaleString()}
                    </div>
                    <div>
                      {t("pluginRuntime.dryRunValidation")}: {dryRun.validation.allowed ? "ready" : dryRun.validation.blockers.join(" · ")}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <span className="skill-meta-pill">
                        package folder {dryRun.package_data_policy.package_folder_action ?? "-"}
                      </span>
                      <span className="skill-meta-pill">
                        plugin-data {dryRun.package_data_policy.plugin_data_folder_action ?? "-"}
                      </span>
                      <span className="skill-meta-pill">
                        data config {dryRun.package_data_policy.plugin_data_config_action ?? "-"}
                      </span>
                      <span className="skill-meta-pill">
                        data storage {dryRun.package_data_policy.plugin_data_storage_action ?? "-"}
                      </span>
                      <span className="skill-meta-pill">
                        runtime data delete {dryRun.package_data_policy.runtime_data_delete_allowed ? "allowed" : "blocked"}
                      </span>
                      <span className="skill-meta-pill">
                        sensitive settings delete {dryRun.package_data_policy.sensitive_settings_delete_allowed ? "allowed" : "blocked"}
                      </span>
                    </div>
                    {dryRun.package_data_policy.notes[0] && (
                      <div className="mt-2 flex gap-2 text-[0.72rem] leading-relaxed">
                        <Archive size={14} className="mt-0.5 flex-shrink-0" />
                        <span>{dryRun.package_data_policy.notes[0]}</span>
                      </div>
                    )}
                  </div>
                )}
                {dryRun?.rollback_notes?.[0] && (
                  <div className="mt-2 flex gap-2 text-[0.72rem] leading-relaxed">
                    <ShieldCheck size={14} className="mt-0.5 flex-shrink-0" />
                    <span>{dryRun.rollback_notes[0]}</span>
                  </div>
                )}
              </div>
            </section>
          </div>

          {plugin.issues.length > 0 && (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
              <div className="mb-1 flex items-center gap-2 font-semibold">
                <AlertTriangle size={14} />
                {t("pluginRuntime.issues")}
              </div>
              {plugin.issues.map((issue) => (
                <div key={`${issue.code}-${issue.phase}`}>{issue.code}: {issue.message}</div>
              ))}
            </div>
          )}

          {audit && audit.audit.length > 0 && (
            <div className="mt-4 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
              <div className="mb-2 font-semibold text-theme-text">
                {t("pluginRuntime.audit.title")}
              </div>
              <div className="space-y-1.5">
                {audit.audit.slice(0, 5).map((record) => (
                  <div
                    key={`${record.action}-${record.created_at}`}
                    className="flex flex-wrap items-center gap-x-2 gap-y-1"
                  >
                    <span className="font-medium text-theme-text">
                      {record.action}
                    </span>
                    <span>{record.next_status}</span>
                    <span>{record.actor_username || record.actor_user_id || "-"}</span>
                    <span>{new Date(record.created_at).toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {isLoadingDetails && (
            <div className="mt-3 text-xs text-theme-text-secondary">
              {t("common.loading")}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export function PluginRuntimePanel({ embedded = false }: PluginRuntimePanelProps) {
  const { t } = useTranslation();
  const {
    data,
    plugins,
    resourcesByPlugin,
    dryRunsByPlugin,
    auditByPlugin,
    settingsByPlugin,
    dataByPlugin,
    packageReviewByPlugin,
    archivedPackages,
    isLoading,
    detailLoadingPlugin,
    stateChangingPlugin,
    error,
    fetchPlugins,
    fetchPluginDetails,
    setPluginEnabled,
    updatePluginSetting,
    reviewPluginPackage,
    resetPluginData,
    exportPlugin,
    importPackage,
    packageImportResult,
    packageRestoreResult,
    lastUninstallResult,
    restoreArchivedPackage,
    uninstallPlugin,
    clearError,
  } = usePluginRuntime();
  const { hasAnyPermission } = useAuth();
  const [expandedPluginId, setExpandedPluginId] = useState<string | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importSourcePath, setImportSourcePath] = useState("");
  const canManageRuntime = hasAnyPermission([Permission.MARKETPLACE_ADMIN]);

  useEffect(() => {
    if (!expandedPluginId) return;
    if (
      resourcesByPlugin[expandedPluginId] &&
      dryRunsByPlugin[expandedPluginId] &&
      settingsByPlugin[expandedPluginId] &&
      (!canManageRuntime || auditByPlugin[expandedPluginId])
    ) {
      return;
    }
    fetchPluginDetails(expandedPluginId, { includeAudit: canManageRuntime });
  }, [
    auditByPlugin,
    canManageRuntime,
    dryRunsByPlugin,
    expandedPluginId,
    fetchPluginDetails,
    resourcesByPlugin,
    settingsByPlugin,
  ]);

  const headerActions = (
    <div className="flex items-center gap-2">
      {canManageRuntime && (
        <Button variant="secondary" onClick={() => setShowImport((value) => !value)} className="h-10">
          <Upload size={16} />
          <span className="hidden sm:inline">{t("pluginRuntime.actions.import")}</span>
        </Button>
      )}
      <Button variant="secondary" onClick={() => fetchPlugins()} className="h-10">
        <RefreshCw size={16} />
        <span className="hidden sm:inline">{t("common.refresh")}</span>
      </Button>
    </div>
  );

  const togglePlugin = (pluginId: string) => {
    setExpandedPluginId((current) => (current === pluginId ? null : pluginId));
  };

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      <PanelHeader
        className="skill-panel-header"
        title={t("pluginRuntime.title")}
        subtitle={embedded ? undefined : t("pluginRuntime.subtitle")}
        icon={embedded ? undefined : <Box size={20} />}
        actions={headerActions}
      />

      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <span>{error}</span>
          <IconButton aria-label={t("common.close")} icon={<AlertTriangle size={18} />} onClick={clearError} />
        </div>
      )}

      <div className="skill-content-area flex-1 overflow-y-auto px-4 py-4 sm:p-5 lg:px-6 lg:py-5">
        {canManageRuntime && showImport && (
          <div className="mb-3 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] px-3 py-3 shadow-sm">
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase text-theme-text-secondary">
              <Upload size={14} />
              <span>{t("pluginRuntime.import.title")}</span>
            </div>
            <input
              value={importSourcePath}
              onChange={(event) => setImportSourcePath(event.target.value)}
              className="w-full rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text outline-none focus:border-[var(--theme-primary)]"
              placeholder={t("pluginRuntime.import.placeholder")}
            />
            {packageImportResult && (
              <div className="mt-2 rounded-md bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
                <div className="font-medium text-theme-text">
                  {packageImportResult.plugin_id} - {packageImportResult.status}
                </div>
                <div className="mt-1 break-all">{packageImportResult.target_path}</div>
                <div className="mt-1 break-all">{packageImportResult.data_dir}</div>
                <div className="mt-1 break-all">
                  sha256 {packageImportResult.integrity.package_sha256.slice(0, 12)} · signature {packageImportResult.integrity.signature_status}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {packageImportResult.actions.map((action: string) => (
                    <span key={action} className="skill-meta-pill">{action}</span>
                  ))}
                </div>
                {packageImportResult.warnings.length > 0 && (
                  <div className="mt-2 text-amber-700 dark:text-amber-300">
                    {packageImportResult.warnings.join(" / ")}
                  </div>
                )}
              </div>
            )}
            {lastUninstallResult && (
              <div className="mt-2 rounded-md bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
                <div className="font-medium text-theme-text">
                  {lastUninstallResult.plugin_id} - {lastUninstallResult.package_action}
                </div>
                {lastUninstallResult.package_archive_path && (
                  <div className="mt-1 break-all">{lastUninstallResult.package_archive_path}</div>
                )}
                <div className="mt-1 break-all">
                  plugin-data {lastUninstallResult.plugin_data_retained ? "retained" : "not retained"}: {lastUninstallResult.plugin_data_dir || "-"}
                </div>
                {lastUninstallResult.package_integrity && (
                  <div className="mt-1 break-all">
                    sha256 {lastUninstallResult.package_integrity.package_sha256.slice(0, 12)} · signature {lastUninstallResult.package_integrity.signature_status}
                  </div>
                )}
              </div>
            )}
            {packageRestoreResult && (
              <div className="mt-2 rounded-md bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
                <div className="font-medium text-theme-text">
                  restored {packageRestoreResult.plugin_id}
                </div>
                <div className="mt-1 break-all">{packageRestoreResult.target_path}</div>
                <div className="mt-1 break-all">plugin-data {packageRestoreResult.data_dir}</div>
                <div className="mt-1 break-all">
                  sha256 {packageRestoreResult.integrity.package_sha256.slice(0, 12)} · signature {packageRestoreResult.integrity.signature_status}
                </div>
              </div>
            )}
            {archivedPackages && archivedPackages.archived.length > 0 && (
              <div className="mt-2 rounded-md bg-[var(--theme-bg)] px-3 py-2 text-xs text-theme-text-secondary">
                <div className="mb-2 font-medium text-theme-text">Archived packages</div>
                <div className="space-y-2">
                  {archivedPackages.archived.slice(0, 5).map((item: ArchivedPluginPackage) => (
                    <div key={item.archive_id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-2 py-2">
                      <div className="min-w-0">
                        <div className="font-medium text-theme-text">{item.plugin_id}</div>
                        <div className="mt-1 max-w-[28rem] truncate">{item.archive_path}</div>
                        <div className="mt-1 max-w-[28rem] truncate">plugin-data {item.data_dir}</div>
                        <div className="mt-1 max-w-[28rem] truncate">
                          sha256 {item.integrity.package_sha256.slice(0, 12)} · signature {item.integrity.signature_status}
                        </div>
                      </div>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={!item.valid || isLoading}
                        onClick={() => {
                          void restoreArchivedPackage(item.archive_id);
                        }}
                      >
                        Restore
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs text-theme-text-secondary">
                {t("pluginRuntime.import.note")}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!importSourcePath.trim() || isLoading}
                  onClick={() => {
                    void importPackage(importSourcePath, true);
                  }}
                >
                  {t("pluginRuntime.import.dryRun")}
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  disabled={!importSourcePath.trim() || isLoading}
                  onClick={() => {
                    void importPackage(importSourcePath, false).then((ok) => {
                      if (ok) {
                        setImportSourcePath("");
                      }
                    });
                  }}
                >
                  {t("pluginRuntime.actions.import")}
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="mb-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <PluginMetric label={t("pluginRuntime.summary.plugins")} value={data?.total ?? plugins.length} />
          <PluginMetric label={t("pluginRuntime.summary.mode")} value={data?.runtime.mode ?? "-"} />
          <PluginMetric label={t("pluginRuntime.summary.hotInstall")} value={data?.runtime.supports_hot_install ? "on" : "off"} />
          <PluginMetric label="Package integrity" value={data?.runtime.supports_package_integrity ? "on" : "off"} />
        </div>
        {data?.runtime.requires_signed_user_installed_enable && (
          <div className="mb-3 rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg-subtle)] px-3 py-2 text-xs text-theme-text-secondary">
            User-installed unsigned plugin packages stay disabled until local review or signature verification is available.
          </div>
        )}

        <div className="mb-3 rounded-lg border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-sm">
          <button
            type="button"
            onClick={() => setShowDiagnostics((value) => !value)}
            className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left"
          >
            <div className="min-w-0">
              <div className="text-xs font-semibold uppercase text-theme-text-secondary">
                {t("pluginRuntime.diagnostics.title")}
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {data?.runtime.acceptance_matrix && (
                  <CompactStat
                    label={t("pluginRuntime.acceptance.title")}
                    value={`${data.runtime.acceptance_matrix.passed_count}/${data.runtime.acceptance_matrix.total}`}
                  />
                )}
                {data?.runtime.phase_progress && (
                  <CompactStat
                    label={t("pluginRuntime.progress.title")}
                    value={`${data.runtime.phase_progress.filter((phase) => phase.passed).length}/${data.runtime.phase_progress.length}`}
                  />
                )}
                {data?.runtime.guard_surfaces && (
                  <CompactStat
                    label={t("pluginRuntime.guardMatrix.title")}
                    value={data.runtime.guard_surfaces.length}
                  />
                )}
              </div>
            </div>
            <ChevronDown
              size={16}
              className={`flex-shrink-0 transition-transform ${showDiagnostics ? "rotate-180" : ""}`}
            />
          </button>
          {showDiagnostics && (
            <div className="border-t border-[var(--theme-border)] px-3 pb-3 pt-3">
              <MigrationProgressOverview
                phases={data?.runtime.phase_progress}
                feedbackMigration={data?.runtime.feedback_migration}
              />

              {data?.runtime.guard_surfaces && (
                <GuardSurfaceMatrix surfaces={data.runtime.guard_surfaces} />
              )}

              <AcceptanceMatrixOverview matrix={data?.runtime.acceptance_matrix} />

              <PluginOwnershipOverview plugins={plugins} />
            </div>
          )}
        </div>

        {isLoading && plugins.length === 0 ? (
          <EmptyState icon={<Plug size={28} />} title={t("common.loading")} />
        ) : plugins.length === 0 ? (
          <EmptyState
            icon={<Plug size={28} />}
            title={t("pluginRuntime.emptyTitle")}
            description={t("pluginRuntime.emptyDescription")}
          />
        ) : (
          <div className="space-y-2">
            {plugins.map((plugin) => (
              <PluginCard
                key={plugin.plugin_id}
                plugin={plugin}
                isExpanded={expandedPluginId === plugin.plugin_id}
                isLoadingDetails={detailLoadingPlugin === plugin.plugin_id}
                resources={resourcesByPlugin[plugin.plugin_id]}
                dryRun={dryRunsByPlugin[plugin.plugin_id]}
                audit={auditByPlugin[plugin.plugin_id]}
                settings={settingsByPlugin[plugin.plugin_id]}
                pluginData={dataByPlugin[plugin.plugin_id]}
                packageReview={packageReviewByPlugin[plugin.plugin_id]}
                runtimePlugins={plugins}
                canManageRuntime={canManageRuntime}
                isChangingState={stateChangingPlugin === plugin.plugin_id}
                onToggle={() => togglePlugin(plugin.plugin_id)}
                onSetEnabled={(pluginId, enabled) => {
                  void setPluginEnabled(pluginId, enabled);
                }}
                onUpdateSetting={updatePluginSetting}
                onReviewPackage={(pluginId) => {
                  void reviewPluginPackage(pluginId, "local package hash review from Extension Center");
                }}
                onResetPluginData={(pluginId) => {
                  if (!window.confirm("Reset plugin-data current config? Existing current.json will be backed up first.")) return;
                  void resetPluginData(pluginId);
                }}
                onExportPlugin={(pluginId) => {
                  void exportPlugin(pluginId);
                }}
                onUninstallPlugin={(pluginId) => {
                  if (!window.confirm(t("pluginRuntime.uninstall.confirm"))) return;
                  void uninstallPlugin(pluginId);
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
