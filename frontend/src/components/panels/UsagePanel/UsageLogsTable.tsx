import { Activity, Bot, FileText, Clock } from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatDateTimeShort } from "../../../utils/datetime";
import type { UsageLog } from "../../../types/usage";
import { fmt, fmtDur } from "./formatters";

function StatusPill({ status }: { status: string }) {
  const { t } = useTranslation();
  const ok = status === "completed";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium tabular-nums ${
        ok
          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          : "bg-red-500/10 text-red-500 dark:text-red-400"
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          ok
            ? "bg-emerald-500 animate-[status-ok-pulse_2s_ease-in-out_infinite]"
            : "bg-red-500"
        }`}
      />
      {ok ? t("usage.statusOk") : t("usage.statusError")}
    </span>
  );
}

function SectionHeader({
  shown,
  total,
  page,
  pageSize,
  title,
}: {
  shown: number;
  total: number;
  page: number;
  pageSize: number;
  title: string;
}) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(start + shown - 1, total);

  return (
    <div className="usage-section-header mb-4 flex items-center justify-between gap-4 sm:mb-5">
      <div className="flex items-center gap-3 sm:gap-3.5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--usage-icon-bg)] text-[var(--theme-primary)] sm:h-9 sm:w-9">
          <FileText size={15} strokeWidth={2} />
        </div>
        <h2 className="truncate text-[13px] font-bold tracking-tight text-theme-text sm:text-sm">
          {title}
        </h2>
      </div>
      {total > 0 && (
        <span className="shrink-0 text-[11px] tabular-nums text-theme-text-tertiary">
          {start}–{end} / {total}
        </span>
      )}
    </div>
  );
}

// ── Desktop Table (lg+) ──

function DesktopTable({
  logs,
  isAdmin,
  hasAnyCache,
}: {
  logs: UsageLog[];
  isAdmin: boolean;
  hasAnyCache: boolean;
}) {
  const { t } = useTranslation();
  const desktopGridTemplate = isAdmin
    ? hasAnyCache
      ? "9.5rem 11rem minmax(8rem,.7fr) minmax(7rem,.9fr) minmax(7rem,.85fr) 5.75rem 5.75rem 5.75rem 6.25rem 5rem 5rem"
      : "9.5rem 11rem minmax(9rem,.8fr) minmax(7rem,.9fr) minmax(7rem,.9fr) 5.75rem 5.75rem 6.25rem 5rem 5rem"
    : hasAnyCache
      ? "9.5rem minmax(9rem,.85fr) minmax(7rem,.9fr) minmax(7rem,.95fr) 5.75rem 5.75rem 5.75rem 6.25rem 5rem 5rem"
      : "9.5rem minmax(9rem,.9fr) minmax(7rem,.9fr) minmax(7rem,1fr) 5.75rem 5.75rem 6.25rem 5rem 5rem";
  const headerCellClass =
    "whitespace-nowrap px-4 py-3 text-[11px] font-medium uppercase tracking-wider text-theme-text-tertiary";
  const textCellClass =
    "min-w-0 whitespace-nowrap px-4 py-3 text-[12px] text-theme-text-secondary";
  const numericCellClass =
    "min-w-0 whitespace-nowrap px-4 py-3 text-right text-[12px] tabular-nums text-theme-text-secondary";

  return (
    <div className="hidden lg:block">
      <div className="usage-surface overflow-x-auto rounded-xl">
        <div className="min-w-[1080px]">
          <div
            className="sticky top-0 z-10 grid border-b border-[var(--usage-border)] bg-[var(--usage-inset-bg)]/70"
            style={{ gridTemplateColumns: desktopGridTemplate }}
          >
            <div className={`${headerCellClass} text-left`}>
              {t("usage.time")}
            </div>
            {isAdmin && (
              <div className={`${headerCellClass} text-left`}>
                {t("usage.user")}
              </div>
            )}
            <div className={`${headerCellClass} text-left`}>
              {t("usage.model")}
            </div>
            <div className={`${headerCellClass} text-left`}>
              {t("usage.agent")}
            </div>
            <div className={`${headerCellClass} text-left`}>
              {t("usage.roleOrTeam")}
            </div>
            <div className={`${headerCellClass} text-right`}>
              {t("usage.inTokens")}
            </div>
            <div className={`${headerCellClass} text-right`}>
              {t("usage.outTokens")}
            </div>
            {hasAnyCache && (
              <div className={`${headerCellClass} text-right`}>
                {t("usage.cache")}
              </div>
            )}
            <div className={`${headerCellClass} text-right`}>
              {t("usage.total")}
            </div>
            <div className={`${headerCellClass} text-right`}>
              {t("usage.duration")}
            </div>
            <div className={`${headerCellClass} text-center`}>
              {t("usage.status")}
            </div>
          </div>
          <div>
            {logs.map((log) => {
              const personaOrTeam = [log.persona_preset_name, log.team_name]
                .filter(Boolean)
                .join(" · ");
              return (
                <div
                  key={log.trace_id}
                  className="usage-table-row grid items-center border-b border-[var(--usage-border)] transition-colors duration-150 last:border-b-0 hover:bg-[var(--usage-surface-hover)]"
                  style={{ gridTemplateColumns: desktopGridTemplate }}
                >
                  <div className={`${textCellClass} tabular-nums`}>
                    {log.started_at ? formatDateTimeShort(log.started_at) : "-"}
                  </div>
                  {isAdmin && (
                    <div className="min-w-0 whitespace-nowrap px-4 py-3">
                      <div className="flex min-w-0 items-center gap-2">
                        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--usage-icon-bg)] text-[10px] font-bold text-[var(--theme-primary)] ring-1 ring-inset ring-[var(--usage-border)]">
                          {(log.username || "-").charAt(0).toUpperCase()}
                        </div>
                        <span className="min-w-0 truncate text-[12px] text-theme-text">
                          {log.username || "-"}
                        </span>
                      </div>
                    </div>
                  )}
                  <div className={textCellClass}>
                    <span className="block truncate tabular-nums">
                      {log.model || "-"}
                    </span>
                  </div>
                  <div className={textCellClass}>
                    <span className="block truncate font-medium">
                      {log.agent_name || "-"}
                    </span>
                  </div>
                  <div className="min-w-0 whitespace-nowrap px-4 py-3 text-[12px] text-theme-text-tertiary">
                    <span className="block truncate">
                      {personaOrTeam || "-"}
                    </span>
                  </div>
                  <div className={numericCellClass}>
                    {fmt(log.input_tokens)}
                  </div>
                  <div className={numericCellClass}>
                    {fmt(log.output_tokens)}
                  </div>
                  {hasAnyCache && (
                    <div
                      className={`${numericCellClass} text-theme-text-tertiary`}
                    >
                      {fmt(log.cache_read_tokens)}
                    </div>
                  )}
                  <div className="min-w-0 whitespace-nowrap px-4 py-3 text-right text-[12px] font-semibold tabular-nums text-[var(--theme-primary)]">
                    {fmt(log.total_tokens)}
                  </div>
                  <div className="min-w-0 whitespace-nowrap px-4 py-3 text-right text-[12px] tabular-nums text-theme-text-tertiary">
                    {fmtDur(log.duration)}
                  </div>
                  <div className="min-w-0 whitespace-nowrap px-4 py-3 text-center">
                    <StatusPill status={log.status} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Tablet Row (sm → lg) ──

function TabletRow({ log, isAdmin }: { log: UsageLog; isAdmin: boolean }) {
  const { t } = useTranslation();
  const personaOrTeam = [log.persona_preset_name, log.team_name]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="usage-surface rounded-xl px-4 py-4 transition-all duration-150 hover:border-[var(--usage-border-hover)]">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <code className="min-w-0 truncate text-[12px] font-semibold text-theme-text tabular-nums">
              {log.model || "-"}
            </code>
            <StatusPill status={log.status} />
          </div>
          <p className="mt-1 truncate text-[11px] font-medium text-theme-text-secondary">
            {log.agent_name || "-"}
          </p>
          <p className="mt-0.5 truncate text-[10px] text-theme-text-tertiary">
            {personaOrTeam || "-"}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[12px] font-medium tabular-nums text-theme-text-secondary">
            {log.started_at ? formatDateTimeShort(log.started_at) : "-"}
          </p>
          <p className="text-[10px] tabular-nums text-theme-text-tertiary">
            {fmtDur(log.duration)}
          </p>
          {isAdmin && log.username && (
            <p className="mt-0.5 max-w-28 truncate text-[10px] text-theme-text-tertiary">
              {log.username}
            </p>
          )}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-4 gap-2 rounded-lg bg-[var(--usage-inset-bg)] px-3 py-3 text-right">
        {[
          [t("usage.inTokens"), fmt(log.input_tokens), false],
          [t("usage.outTokens"), fmt(log.output_tokens), false],
          [t("usage.cache"), fmt(log.cache_read_tokens), false],
          [t("usage.total"), fmt(log.total_tokens), true],
        ].map(([label, value, strong]) => (
          <div key={String(label)} className="min-w-0">
            <span className="block text-[9px] text-theme-text-tertiary">
              {label}
            </span>
            <span
              className={`mt-0.5 block truncate text-[12px] font-semibold tabular-nums ${
                strong
                  ? "text-[var(--theme-primary)]"
                  : "text-theme-text-secondary"
              }`}
            >
              {value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Mobile Card (< sm) ──

function MobileCard({ log, isAdmin }: { log: UsageLog; isAdmin: boolean }) {
  const { t } = useTranslation();
  const ok = log.status === "completed";
  const personaOrTeam = [log.persona_preset_name, log.team_name]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="usage-surface usage-mobile-card overflow-hidden rounded-2xl transition-all duration-200 active:scale-[0.98]">
      <div className="px-4 pt-4 pb-3.5">
        {/* Header: icon + model info + status */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <div
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                ok
                  ? "bg-emerald-500/[0.08] text-emerald-600 dark:text-emerald-400"
                  : "bg-red-500/[0.08] text-red-500 dark:text-red-400"
              }`}
            >
              <Bot size={16} strokeWidth={2} />
            </div>
            <div className="min-w-0 flex-1">
              <code className="block truncate text-[13px] font-bold text-theme-text tabular-nums">
                {log.model || "-"}
              </code>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <span className="usage-soft-pill text-[10px] font-medium text-theme-text-secondary">
                  {log.agent_name || "-"}
                </span>
                {personaOrTeam && (
                  <span className="usage-soft-pill text-[10px] text-theme-text-tertiary">
                    {personaOrTeam}
                  </span>
                )}
              </div>
            </div>
          </div>
          <StatusPill status={log.status} />
        </div>

        {/* Token metrics — segmented bar */}
        <div className="usage-metrics-bar mt-4 grid grid-cols-4 overflow-hidden rounded-xl">
          {[
            [t("usage.inTokens"), fmt(log.input_tokens), false],
            [t("usage.outTokens"), fmt(log.output_tokens), false],
            [t("usage.cacheRead"), fmt(log.cache_read_tokens), false],
            [t("usage.totalTokens"), fmt(log.total_tokens), true],
          ].map(([label, value, strong], i) => (
            <div
              key={String(label)}
              className={`flex flex-col items-center py-2.5 ${
                i > 0 ? "border-l border-[var(--usage-border)]" : ""
              }`}
            >
              <span className="text-[8px] font-semibold uppercase tracking-widest text-theme-text-tertiary">
                {label}
              </span>
              <span
                className={`mt-1 text-[14px] tabular-nums ${
                  strong
                    ? "font-bold text-[var(--theme-primary)]"
                    : "font-semibold text-theme-text"
                }`}
              >
                {value}
              </span>
            </div>
          ))}
        </div>

        {/* Metadata footer */}
        <div className="mt-3 flex items-center justify-between text-[10px] text-theme-text-tertiary">
          <div className="flex min-w-0 items-center gap-1">
            <Clock size={9} className="shrink-0 opacity-40" />
            <span className="truncate tabular-nums">
              {log.started_at ? formatDateTimeShort(log.started_at) : "-"}
            </span>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {isAdmin && log.username && (
              <span className="max-w-20 truncate text-theme-text-secondary">
                {log.username}
              </span>
            )}
            {log.duration > 0 && (
              <span className="tabular-nums">{fmtDur(log.duration)}</span>
            )}
            {log.source === "scheduled_task" && (
              <span className="font-medium text-[var(--theme-primary)]">
                {t("usage.scheduledBadge")}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main Export ──

export function UsageLogsTable({
  logs,
  total,
  page,
  pageSize,
  isAdmin,
  hasAnyCache,
}: {
  logs: UsageLog[];
  total: number;
  page: number;
  pageSize: number;
  isAdmin: boolean;
  hasAnyCache: boolean;
}) {
  const { t } = useTranslation();

  if (logs.length === 0) {
    return (
      <div className="usage-empty-state flex flex-col items-center justify-center py-16 text-center sm:py-20">
        <div className="mb-4 rounded-2xl bg-[var(--glass-bg-subtle)] p-5 ring-1 ring-inset ring-[var(--theme-border-faint)]">
          <Activity size={28} className="text-theme-text-tertiary/25" />
        </div>
        <p className="text-sm font-medium text-theme-text-secondary/60">
          {t("usage.noUsage")}
        </p>
        <p className="mt-1.5 text-xs text-theme-text-tertiary/50">
          {t("usage.noUsageHint")}
        </p>
      </div>
    );
  }

  return (
    <>
      <SectionHeader
        shown={logs.length}
        total={total}
        page={page}
        pageSize={pageSize}
        title={t("usage.logDetails")}
      />

      {/* Desktop table */}
      <DesktopTable logs={logs} isAdmin={isAdmin} hasAnyCache={hasAnyCache} />

      {/* Tablet rows */}
      <div className="hidden sm:block lg:hidden">
        <div className="space-y-4">
          {logs.map((log) => (
            <TabletRow key={log.trace_id} log={log} isAdmin={isAdmin} />
          ))}
        </div>
      </div>

      {/* Mobile cards */}
      <div className="space-y-4 pb-5 sm:hidden">
        {logs.map((log) => (
          <MobileCard key={log.trace_id} log={log} isAdmin={isAdmin} />
        ))}
      </div>
    </>
  );
}
