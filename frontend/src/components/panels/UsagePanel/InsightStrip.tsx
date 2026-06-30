import {
  AlertTriangle,
  DatabaseZap,
  Gauge,
  Target,
  TimerReset,
  Wrench,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UsageDashboardResponse } from "../../../types/usage";
import { fmt, fmtDur, pct, precise, shortDate } from "./formatters";

interface Insight {
  icon: typeof Gauge;
  label: string;
  value: string;
  detail: string;
  tone?: string;
}

export function InsightStrip({
  dashboard,
}: {
  dashboard: UsageDashboardResponse;
}) {
  const { t } = useTranslation();
  const s = dashboard.summary;
  const peakDay = s.peak_day;
  const failureTone =
    s.failed_requests > 0
      ? "text-amber-600 dark:text-amber-400"
      : "text-emerald-500 dark:text-emerald-400";

  const insights: Insight[] = [
    {
      icon: Gauge,
      label: t("usage.insight.avgPerRequest"),
      value: t("usage.tokensValue", {
        count: fmt(Math.round(s.avg_tokens_per_request)),
      }),
      detail: fmtDur(s.avg_duration_per_request),
    },
    {
      icon: Target,
      label: t("usage.insight.automationShare"),
      value: pct(s.scheduled_share),
      detail: t("usage.insight.scheduledExecutions", {
        count: s.scheduled_runs,
      }),
    },
    {
      icon: DatabaseZap,
      label: t("usage.insight.cacheReuse"),
      value: pct(s.cache_read_share),
      detail: t("usage.tokensValue", { count: fmt(s.total_cache_read_tokens) }),
    },
    {
      icon: AlertTriangle,
      label: t("usage.insight.failedRequests"),
      value: fmt(s.failed_requests),
      detail: t("usage.insight.successRate", { rate: pct(s.success_rate) }),
      tone: failureTone,
    },
    {
      icon: TimerReset,
      label: t("usage.insight.maxDuration"),
      value: fmtDur(s.max_duration),
      detail: peakDay
        ? t("usage.insight.peakAt", { date: shortDate(peakDay.date) })
        : t("usage.insight.noPeak"),
    },
    {
      icon: Wrench,
      label: t("usage.insight.toolDensity"),
      value: precise(s.tool_calls_per_request),
      detail: t("usage.insight.perRequest"),
    },
  ];

  return (
    <div className="usage-insight-strip usage-surface grid grid-cols-2 overflow-hidden rounded-xl sm:grid-cols-3 xl:grid-cols-6">
      {insights.map((item) => (
        <div
          key={item.label}
          className="min-w-0 border-r border-b border-[var(--usage-border)] px-3.5 py-4 transition-colors duration-200 hover:bg-[var(--usage-surface-hover)] sm:px-4 sm:py-5 xl:border-b-0"
        >
          <div className="mb-1 flex items-center gap-1.5 sm:gap-2">
            <item.icon
              size={12}
              strokeWidth={2}
              className="shrink-0 text-theme-text-tertiary"
            />
            <span className="min-w-0 truncate text-[10px] font-medium uppercase tracking-wider text-theme-text-tertiary sm:text-[11px]">
              {item.label}
            </span>
          </div>
          <p
            className={`truncate text-[15px] font-extrabold tabular-nums leading-tight text-theme-text sm:text-base ${
              item.tone ?? ""
            }`}
          >
            {item.value}
          </p>
          <p className="mt-1 truncate text-[10px] leading-snug text-theme-text-tertiary">
            {item.detail}
          </p>
        </div>
      ))}
    </div>
  );
}
