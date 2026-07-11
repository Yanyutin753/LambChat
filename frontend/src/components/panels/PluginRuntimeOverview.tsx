import { Flag, ListChecks, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PluginRuntimeListResponse } from "../../types";

export function PluginMetric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-md border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2">
      <div className="text-[0.68rem] font-medium uppercase text-theme-text-secondary">
        {label}
      </div>
      <div className="mt-1 text-sm font-semibold text-theme-text">{value}</div>
    </div>
  );
}

export function MigrationProgressOverview({
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

export function GuardSurfaceMatrix({
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

export function AcceptanceMatrixOverview({
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
          {matrix.passed
            ? t("pluginRuntime.acceptance.passed")
            : t("pluginRuntime.acceptance.missing")}
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
