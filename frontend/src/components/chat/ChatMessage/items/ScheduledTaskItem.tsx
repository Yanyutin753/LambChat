import { memo, useMemo, useState } from "react";
import { clsx } from "clsx";
import {
  CalendarClock,
  Clock,
  CheckCircle2,
  MessageSquare,
  Zap,
  AlertCircle,
  Ban,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractText } from "./toolUtils";
import { openPersistentToolPanel } from "./persistentToolPanelState";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { DetailSection } from "./DetailSection";

// ── helpers ──────────────────────────────────────────────────────────

function getActionLabel(
  toolName: string,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const map: Record<string, string> = {
    scheduled_task_create: "chat.message.toolScheduledTaskCreate",
    scheduled_task_list: "chat.message.toolScheduledTaskList",
    scheduled_task_get: "chat.message.toolScheduledTaskGet",
    scheduled_task_update: "chat.message.toolScheduledTaskUpdate",
    scheduled_task_pause: "chat.message.toolScheduledTaskPause",
    scheduled_task_resume: "chat.message.toolScheduledTaskResume",
    scheduled_task_delete: "chat.message.toolScheduledTaskDelete",
    scheduled_task_run: "chat.message.toolScheduledTaskRun",
  };
  return t(map[toolName] || "chat.message.toolScheduledTask");
}

function TriggerBadge({
  type,
  t,
}: {
  type: string;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const styles: Record<string, string> = {
    date: "bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))] text-theme-text-secondary ring-1 ring-inset ring-[color-mix(in_srgb,var(--theme-primary)_16%,var(--theme-border))]",
    interval:
      "bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))] text-theme-text-secondary ring-1 ring-inset ring-[color-mix(in_srgb,var(--theme-primary)_16%,var(--theme-border))]",
    cron: "bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))] text-theme-text-secondary ring-1 ring-inset ring-[color-mix(in_srgb,var(--theme-primary)_16%,var(--theme-border))]",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-xs font-medium",
        styles[type] || styles.date,
      )}
    >
      <Clock size={10} className="opacity-70" />
      {t(`scheduledTask.${type}`)}
    </span>
  );
}

function StatusBadge({
  status,
  enabled,
  t,
}: {
  status?: string;
  enabled?: boolean;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  if (!enabled) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-xs">
        <AlertCircle size={10} />
        {t("scheduledTask.paused")}
      </span>
    );
  }
  const isActive = status === "active" || status === "running";
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium",
        isActive
          ? "bg-[color-mix(in_srgb,#10b981_10%,var(--theme-bg-card))] text-emerald-700 dark:text-emerald-300 ring-1 ring-inset ring-[color-mix(in_srgb,#10b981_20%,transparent)]"
          : "bg-theme-bg-subtle text-theme-text-tertiary ring-1 ring-inset ring-theme-border",
      )}
    >
      <span
        className={clsx(
          "w-1.5 h-1.5 rounded-full",
          isActive ? "bg-emerald-500" : "bg-theme-text-tertiary",
        )}
      />
      {t(`scheduledTask.${status || "statusUnknown"}`)}
    </span>
  );
}

function formatSchedule(
  preview: Record<string, unknown> | null | undefined,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  if (!preview) return "";
  const trigger = preview.trigger_type as string | undefined;
  const config = preview.trigger_config as Record<string, unknown> | undefined;
  if (trigger === "interval" && config?.seconds) {
    const s = Number(config.seconds);
    if (s >= 86400)
      return t("scheduledTask.everyDays", { count: Math.round(s / 86400) });
    if (s >= 3600)
      return t("scheduledTask.everyHours", { count: Math.round(s / 3600) });
    if (s >= 60)
      return t("scheduledTask.everyMinutes", { count: Math.round(s / 60) });
    return t("scheduledTask.everySeconds", { count: s });
  }
  if (trigger === "cron" && config) {
    const parts = [
      config.hour,
      config.minute,
      config.day_of_week,
      config.day_of_month,
    ]
      .filter(Boolean)
      .map(String);
    return t("scheduledTask.cronExpr", { expr: parts.join(" ") });
  }
  if (trigger === "date") {
    if (preview.run_at) return String(preview.run_at);
    if (config?.seconds)
      return t("scheduledTask.inSeconds", { seconds: Number(config.seconds) });
    return t("scheduledTask.once");
  }
  return "";
}

interface ParsedResult {
  task: Record<string, unknown> | null;
  preview: Record<string, unknown> | null;
  message: string;
  tasks: Array<Record<string, unknown>>;
  isList: boolean;
  /** Populated when the result is a rejection response like {success:false, reason:"rejected"} */
  rejection: {
    reason: string;
    message: string;
    preview: Record<string, unknown> | null;
  } | null;
}

function parseResult(
  result: string | Record<string, unknown> | undefined,
): ParsedResult {
  const empty: ParsedResult = {
    task: null,
    preview: null,
    message: "",
    tasks: [],
    isList: false,
    rejection: null,
  };
  if (!result) return empty;

  const text = extractText(result);
  if (!text) return empty;

  try {
    const obj = JSON.parse(text);

    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      // ── Rejection shape: {success:false, action:"not_created", reason, preview, message} ──
      if (
        obj.success === false &&
        typeof obj.reason === "string" &&
        !obj.task
      ) {
        return {
          task: null,
          preview: null,
          message: "",
          tasks: [],
          isList: false,
          rejection: {
            reason: obj.reason,
            message: String(obj.message || ""),
            preview:
              obj.preview && typeof obj.preview === "object"
                ? (obj.preview as Record<string, unknown>)
                : null,
          },
        };
      }

      // create/update/delete returns { task, preview, message }
      if (obj.task && typeof obj.task === "object") {
        return {
          task: obj.task as Record<string, unknown>,
          preview: (obj.preview as Record<string, unknown>) || null,
          message: String(obj.message || ""),
          tasks: [],
          isList: false,
          rejection: null,
        };
      }
      // list returns an array or { tasks: [...] }
      if (Array.isArray(obj)) {
        return {
          task: null,
          preview: null,
          message: "",
          tasks: obj,
          isList: true,
          rejection: null,
        };
      }
      if (Array.isArray(obj.tasks)) {
        return {
          task: null,
          preview: null,
          message: "",
          tasks: obj.tasks,
          isList: true,
          rejection: null,
        };
      }
      // single task from get/detail
      if (obj.id && obj.name) {
        return {
          task: obj as Record<string, unknown>,
          preview: null,
          message: "",
          tasks: [],
          isList: false,
          rejection: null,
        };
      }
    }
  } catch {
    // not JSON
  }

  return { ...empty, message: text };
}

// ── Rejection card (inline, themed for scheduled tasks) ──────────────

function RejectionCard({
  rejection,
  t,
  compact,
}: {
  rejection: NonNullable<ParsedResult["rejection"]>;
  t: (key: string, opts?: Record<string, unknown>) => string;
  compact: boolean;
}) {
  const [showDetails, setShowDetails] = useState(false);
  const taskName =
    rejection.preview && typeof rejection.preview.name === "string"
      ? (rejection.preview.name as string)
      : "";
  const description =
    rejection.preview && typeof rejection.preview.description === "string"
      ? (rejection.preview.description as string)
      : "";
  const schedule =
    rejection.preview && typeof rejection.preview.schedule === "string"
      ? (rejection.preview.schedule as string)
      : "";
  const triggerType =
    rejection.preview && typeof rejection.preview.trigger_type === "string"
      ? (rejection.preview.trigger_type as string)
      : "";
  const summary = rejection.message || t("scheduledTask.creationRejected");

  if (compact) {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-[color-mix(in_srgb,var(--theme-primary)_10%,var(--theme-border))] bg-[color-mix(in_srgb,var(--theme-bg-card)_72%,transparent)] px-2.5 py-2">
        <Ban size={12} className="shrink-0 mt-0.5 text-theme-text-tertiary" />
        <span className="text-[11px] text-theme-text-secondary truncate min-w-0">
          {summary.length > 80 ? summary.slice(0, 77) + "…" : summary}
        </span>
      </div>
    );
  }

  return (
    <div className="relative rounded-xl border border-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))] overflow-hidden bg-theme-bg-card shadow-[0_12px_28px_-24px_color-mix(in_srgb,var(--theme-primary)_45%,transparent)]">
      {/* Top accent bar */}
      <div className="h-0.5 bg-gradient-to-r from-[var(--theme-primary)] via-[color-mix(in_srgb,var(--theme-primary)_38%,transparent)] to-transparent" />

      <div className="p-3 space-y-2">
        {/* Header row */}
        <div className="flex items-start gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))] ring-1 ring-inset ring-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))]">
            <Ban size={15} className="text-theme-text-tertiary" />
          </div>
          <div className="min-w-0 flex-1 space-y-0.5">
            {taskName && (
              <p className="text-sm font-semibold text-theme-text truncate">
                {taskName}
              </p>
            )}
            <p className="text-xs text-theme-text-secondary">{summary}</p>
          </div>
        </div>

        {/* Metadata badges */}
        {(schedule || triggerType) && (
          <div className="flex flex-wrap gap-1.5 pl-[2.75rem]">
            {triggerType && <TriggerBadge type={triggerType} t={t} />}
            {schedule && (
              <span className="px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-xs font-mono leading-relaxed">
                {schedule}
              </span>
            )}
          </div>
        )}

        {/* Description (collapsed) */}
        {description && !showDetails && (
          <p className="text-[11px] text-theme-text-tertiary line-clamp-2 pl-[2.75rem]">
            {description}
          </p>
        )}

        {/* Expanded details */}
        {showDetails && (
          <div className="space-y-2 pt-2 mt-2 border-t border-theme-border pl-[2.75rem]">
            {description && (
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wider text-theme-text-tertiary mb-0.5">
                  {t("chat.message.description")}
                </p>
                <p className="text-xs text-theme-text-secondary whitespace-pre-wrap break-words">
                  {description}
                </p>
              </div>
            )}
            {rejection.preview && (
              <div>
                <p className="text-[10px] font-medium uppercase tracking-wider text-theme-text-tertiary mb-0.5">
                  {t("chat.message.details")}
                </p>
                <pre className="text-[11px] text-theme-text-tertiary overflow-y-auto whitespace-pre-wrap break-words max-h-48 min-w-0 p-2.5 rounded-lg bg-theme-bg border border-theme-border">
                  {JSON.stringify(rejection.preview, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* Expand toggle */}
        {(description || rejection.preview) && (
          <div className="pl-[2.75rem]">
            <button
              onClick={() => setShowDetails((v) => !v)}
              className="flex items-center gap-0.5 text-[11px] text-theme-text-tertiary transition-colors hover:text-theme-text-secondary"
            >
              {showDetails ? (
                <ChevronUp size={11} />
              ) : (
                <ChevronDown size={11} />
              )}
              {showDetails
                ? t("chat.message.collapse")
                : t("chat.message.expandAll")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── component ──────────────────────────────────────────────────────────

const ScheduledTaskItem = memo(function ScheduledTaskItem({
  toolName,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  toolName: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );

  const actionLabel = getActionLabel(toolName, t);
  const taskName = (args.name as string) || "";
  const triggerType = (args.trigger_type as string) || "";
  const action = (args.action as string) || "";

  const parsed = useMemo(() => parseResult(result), [result]);

  // Merge args + result data
  const task = parsed.task;
  const preview = parsed.preview;
  const resultMessage = parsed.message;
  const isList = parsed.isList;
  const tasks = parsed.tasks;
  const rejection = parsed.rejection;

  // When rejected, extract name from the rejection preview for the pill label
  const rejectionTaskName = rejection?.preview?.name
    ? String(rejection.preview.name)
    : "";

  const displayName = String(task?.name || taskName || rejectionTaskName || "");
  const trigger = String(
    task?.trigger_type || triggerType || preview?.trigger_type || "",
  );
  const schedule = formatSchedule(preview, t) || formatSchedule(parsed.task, t);
  const taskMessage = String(
    preview?.message ||
      (task?.input_payload as Record<string, unknown> | undefined)?.message ||
      args.message ||
      "",
  );
  const effect = String(preview?.effect || "");
  const status = typeof task?.status === "string" ? task.status : undefined;
  const enabled = typeof task?.enabled === "boolean" ? task.enabled : undefined;
  const totalRuns =
    typeof task?.total_runs === "number" ? task.total_runs : undefined;

  const canExpand = !!displayName || !!trigger || !!result;
  const pillStatus = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const labelSuffix = displayName || action || "";

  // ── detail (panel) content ─────────────────────────────────────────

  const detailContent = canExpand && (
    <div className="p-4 sm:p-5 space-y-3 tool-panel-content">
      {/* Rejection card */}
      {rejection && (
        <RejectionCard rejection={rejection} t={t} compact={false} />
      )}

      {/* Task card (create/update/delete) */}
      {displayName && !isList && (
        <div
          className={clsx(
            "relative flex items-center gap-3 rounded-xl p-3",
            "bg-[color-mix(in_srgb,var(--theme-bg-card)_74%,var(--theme-bg)_26%)] border border-[color-mix(in_srgb,var(--theme-primary)_12%,var(--theme-border))]",
            "hover:border-[color-mix(in_srgb,var(--theme-primary)_26%,var(--theme-border))] transition-colors shadow-[0_1px_2px_rgb(0_0_0/0.04)]",
          )}
        >
          <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 bg-[color-mix(in_srgb,var(--theme-primary)_9%,var(--theme-bg-card))] ring-1 ring-inset ring-[color-mix(in_srgb,var(--theme-primary)_16%,var(--theme-border))]">
            <CalendarClock size={18} className="text-[var(--theme-primary)]" />
          </div>
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="text-sm text-theme-text font-semibold truncate">
              {displayName}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {trigger && <TriggerBadge type={trigger} t={t} />}
              {schedule && (
                <span className="px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-xs font-mono leading-relaxed">
                  {schedule}
                </span>
              )}
              {typeof enabled === "boolean" && (
                <StatusBadge status={status} enabled={enabled} t={t} />
              )}
              {typeof totalRuns === "number" && totalRuns > 0 && (
                <span className="px-2 py-0.5 rounded-md bg-theme-bg-subtle text-theme-text-tertiary text-xs tabular-nums">
                  {t("scheduledTask.runsCount", { count: totalRuns })}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Message prompt */}
      {taskMessage && !isList && (
        <DetailSection
          title={t("chat.message.toolTaskName")}
          icon={<MessageSquare size={12} />}
          defaultExpanded={true}
        >
          <div className="text-sm text-theme-text-secondary whitespace-pre-wrap break-words leading-relaxed">
            {taskMessage}
          </div>
        </DetailSection>
      )}

      {/* Effect description */}
      {effect && !isList && (
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-[color-mix(in_srgb,var(--theme-primary)_6%,var(--theme-bg-card))] border border-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))]">
          <Zap
            size={12}
            className="shrink-0 text-[var(--theme-primary)] mt-0.5"
          />
          <span className="text-xs text-theme-text-secondary leading-relaxed">
            {effect}
          </span>
        </div>
      )}

      {/* Result message (confirmation) */}
      {resultMessage && !isList && (
        <div className="flex items-center gap-2 text-xs">
          <CheckCircle2
            size={13}
            className="shrink-0 text-emerald-500 dark:text-emerald-400"
          />
          <span className="text-theme-text-tertiary">{resultMessage}</span>
        </div>
      )}

      {/* List of tasks */}
      {isList && tasks.length > 0 && (
        <DetailSection
          title={t("chat.message.toolScheduledTaskList")}
          icon={<CalendarClock size={12} />}
          defaultExpanded={true}
          badge={
            <span className="text-[10px] text-theme-text-tertiary tabular-nums">
              {tasks.length}
            </span>
          }
        >
          <div className="space-y-1.5">
            {tasks.map((tk, i) => {
              const tkName = String(tk.name || `Task ${i + 1}`);
              const tkTrigger = tk.trigger_type as string | undefined;
              const tkStatus = tk.status as string | undefined;
              const tkEnabled = tk.enabled as boolean | undefined;
              const tkId = tk.id as string | undefined;
              return (
                <div
                  key={tkId || i}
                  className={clsx(
                    "flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors",
                    "bg-theme-bg border border-theme-border",
                    "hover:border-[color-mix(in_srgb,var(--theme-primary)_24%,var(--theme-border))]",
                  )}
                >
                  <CalendarClock
                    size={14}
                    className="shrink-0 text-[var(--theme-primary)]"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-theme-text font-medium truncate">
                      {tkName}
                    </div>
                  </div>
                  {tkTrigger && (
                    <span className="shrink-0 px-1.5 py-0.5 rounded bg-theme-bg-subtle text-[10px] text-theme-text-tertiary">
                      {t(`scheduledTask.${tkTrigger}`)}
                    </span>
                  )}
                  <StatusBadge
                    status={tkStatus}
                    enabled={tkEnabled !== false}
                    t={t}
                  />
                </div>
              );
            })}
          </div>
        </DetailSection>
      )}

      {/* Pure text fallback (no structured data parsed) */}
      {resultMessage && !displayName && !isList && (
        <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
          {resultMessage}
          <ToolHoverCopyButton
            text={resultMessage}
            position="result"
            copyButtonClassName="!bg-theme-bg-card/80 !rounded-md !border !border-theme-border"
          />
        </pre>
      )}
    </div>
  );

  // ── compact (inline) content ────────────────────────────────────────

  const compactContent = canExpand && (
    <ToolInlineDetails>
      {/* Compact rejection */}
      {rejection && (
        <RejectionCard rejection={rejection} t={t} compact={true} />
      )}

      {!rejection && displayName && !isList && (
        <ToolArgsBlock size="compact">
          <CalendarClock
            size={12}
            className="shrink-0 text-[var(--theme-primary)]"
          />
          <span className="truncate text-theme-text font-medium">
            {displayName}
          </span>
        </ToolArgsBlock>
      )}

      <div className="flex flex-wrap gap-1">
        {trigger && (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[color-mix(in_srgb,var(--theme-primary)_8%,var(--theme-bg-card))] text-theme-text-secondary ring-1 ring-inset ring-[color-mix(in_srgb,var(--theme-primary)_14%,var(--theme-border))] text-[10px] font-medium">
            <Clock size={8} className="opacity-70" />
            {t(`scheduledTask.${trigger}`)}
          </span>
        )}
        {schedule && (
          <span className="px-1.5 py-0.5 rounded bg-theme-bg-subtle text-theme-text-tertiary text-[10px] font-mono">
            {schedule}
          </span>
        )}
        {typeof enabled === "boolean" && (
          <span
            className={clsx(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px]",
              enabled
                ? "bg-emerald-100/60 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400"
                : "bg-theme-bg-subtle text-theme-text-tertiary",
            )}
          >
            <span
              className={clsx(
                "w-1 h-1 rounded-full",
                enabled ? "bg-emerald-500" : "bg-theme-text-tertiary",
              )}
            />
            {status
              ? t(`scheduledTask.${status}`)
              : enabled
                ? t("scheduledTask.active")
                : t("scheduledTask.statusOff")}
          </span>
        )}
      </div>

      {/* Compact confirmation */}
      {resultMessage && !isList && (
        <div className="flex items-center gap-1.5 text-[10px]">
          <CheckCircle2
            size={10}
            className="shrink-0 text-emerald-500 dark:text-emerald-400"
          />
          <span className="text-theme-text-tertiary truncate">
            {resultMessage.length > 120
              ? resultMessage.slice(0, 117) + "…"
              : resultMessage}
          </span>
        </div>
      )}

      {/* Compact list */}
      {isList && tasks.length > 0 && (
        <div className="space-y-1">
          {tasks.slice(0, 6).map((tk, i) => {
            const tkName = String(tk.name || `Task ${i + 1}`);
            const tkTrigger = tk.trigger_type as string | undefined;
            return (
              <div
                key={i}
                className="flex items-center gap-2 px-2 py-1 rounded-md bg-theme-bg border border-theme-border hover:border-[color-mix(in_srgb,var(--theme-primary)_24%,var(--theme-border))] transition-colors"
              >
                <CalendarClock
                  size={10}
                  className="shrink-0 text-[var(--theme-primary)]"
                />
                <span className="text-[10px] text-theme-text truncate flex-1">
                  {tkName}
                </span>
                {tkTrigger && (
                  <span className="shrink-0 text-[9px] text-theme-text-tertiary">
                    {t(`scheduledTask.${tkTrigger}`)}
                  </span>
                )}
              </div>
            );
          })}
          {tasks.length > 6 && (
            <span className="text-[10px] text-theme-text-tertiary pl-2">
              +{tasks.length - 6} more
            </span>
          )}
        </div>
      )}

      {/* Pure text fallback */}
      {resultMessage && !displayName && !isList && (
        <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words overflow-y-auto min-w-0">
          {resultMessage.length > 300
            ? resultMessage.slice(0, 297) + "…"
            : resultMessage}
          <ToolHoverCopyButton text={resultMessage} position="resultCompact" />
        </pre>
      )}
    </ToolInlineDetails>
  );

  return (
    <>
      <CollapsiblePill
        status={pillStatus}
        icon={<CalendarClock size={12} className="shrink-0 opacity-50" />}
        label={`${actionLabel}${labelSuffix ? ` ${labelSuffix}` : ""}`}
        variant="tool"
        expandable={canExpand}
        onPanelOpen={() => {
          if (!canExpand) return;
          openPersistentToolPanel({
            title: actionLabel,
            icon: <CalendarClock size={16} />,
            status: pillStatus,
            subtitle: labelSuffix || undefined,
            children: detailContent,
            footer: durationFooter,
          });
        }}
      >
        {compactContent}
      </CollapsiblePill>
    </>
  );
});

export { ScheduledTaskItem };
