import { useMemo } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot,
} from "recharts";
import { LineChart, TrendingUp, Zap, Calendar, Flame } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UsageDailyPoint } from "../../../types/usage";
import { fmt, fmtDur, normalizeTrendPoints, shortDate } from "./formatters";

// ── Custom tooltip ──
function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-[var(--usage-border)] bg-[var(--theme-bg-card)] px-4 py-2.5 shadow-lg">
      <div className="h-0.5 mb-2 rounded-full bg-[var(--theme-primary)]" />
      <p className="mb-1 text-11 font-medium text-theme-text-tertiary">
        {label}
      </p>
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 text-xs">
          <span
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-theme-text-secondary">{entry.name}</span>
          <span className="ml-auto font-semibold tabular-nums text-theme-text">
            {fmt(entry.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function MiniTrend({ points }: { points: UsageDailyPoint[] }) {
  const { t } = useTranslation();
  const visible = useMemo(
    () => normalizeTrendPoints(points).slice(-14),
    [points],
  );

  const totalTokens = visible.reduce((s, p) => s + p.tokens, 0);
  const totalRequests = visible.reduce((s, p) => s + p.requests, 0);
  const totalScheduled = visible.reduce((s, p) => s + p.scheduled_runs, 0);
  const totalFailures = visible.reduce((s, p) => s + p.failed_requests, 0);
  const totalHours = visible.reduce((s, p) => s + p.duration, 0);
  const activeDays = visible.filter(
    (p) => p.tokens > 0 || p.requests > 0,
  ).length;
  const hasData = visible.some((p) => p.tokens > 0 || p.requests > 0);
  const peakIdx = visible.reduce(
    (best, p, i) => (p.tokens > visible[best].tokens ? i : best),
    0,
  );
  const peakPoint = visible[peakIdx];

  const chartData = useMemo(
    () =>
      visible.map((p) => ({
        date: shortDate(p.date),
        Tokens: p.tokens,
        requests: p.requests,
      })),
    [visible],
  );

  return (
    <div className="usage-surface usage-chart-card overflow-hidden rounded-xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-[var(--usage-border)] px-4 pt-4 pb-3.5 sm:px-5">
        <div className="flex items-center gap-2.5">
          <div className="usage-icon flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--usage-icon-bg)] text-[var(--theme-primary)] sm:h-9 sm:w-9">
            <LineChart size={15} strokeWidth={2} />
          </div>
          <div>
            <h3 className="text-13 font-bold tracking-tight text-theme-text sm:text-sm">
              {t("usage.trend.title")}
            </h3>
            <p className="text-10 text-theme-text-tertiary sm:text-11">
              {t("usage.trend.subtitle")}
            </p>
          </div>
        </div>
        <div className="hidden flex-wrap justify-end gap-1.5 text-10 sm:flex">
          <span className="usage-soft-pill">
            {t("usage.trend.scheduledSuffix", { count: totalScheduled })}
          </span>
          {totalFailures > 0 && (
            <span className="usage-soft-pill text-amber-600 dark:text-amber-400">
              {t("usage.trend.failureSuffix", { count: totalFailures })}
            </span>
          )}
          <span className="usage-soft-pill">{fmtDur(totalHours)}</span>
        </div>
      </div>

      {/* Chart area */}
      <div className="bg-[var(--usage-inset-bg)] px-1 py-2 sm:px-2 sm:py-3">
        {!hasData ? (
          <div className="usage-empty-state flex h-[180px] flex-col items-center justify-center gap-2 text-theme-text-tertiary sm:h-[220px]">
            <LineChart size={24} className="opacity-20" />
            <span className="text-xs">{t("usage.trend.empty")}</span>
          </div>
        ) : (
          <ResponsiveContainer
            width="100%"
            height={180}
            className="sm:!h-[220px]"
          >
            <AreaChart
              data={chartData}
              margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
            >
              <defs>
                <linearGradient id="gradTokens" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor="var(--theme-primary)"
                    stopOpacity={0.3}
                  />
                  <stop
                    offset="95%"
                    stopColor="var(--theme-primary)"
                    stopOpacity={0}
                  />
                </linearGradient>
                <linearGradient id="gradRequests" x1="0" y1="0" x2="0" y2="1">
                  <stop
                    offset="0%"
                    stopColor="var(--usage-chart-secondary)"
                    stopOpacity={0.2}
                  />
                  <stop
                    offset="95%"
                    stopColor="var(--usage-chart-secondary)"
                    stopOpacity={0}
                  />
                </linearGradient>
              </defs>

              <CartesianGrid
                strokeDasharray="3 4"
                stroke="var(--usage-border)"
                vertical={false}
                opacity={0.5}
              />

              <XAxis
                dataKey="date"
                tick={{
                  fill: "var(--theme-text-tertiary)",
                  fontSize: 10,
                }}
                tickLine={false}
                axisLine={false}
                dy={8}
              />

              <YAxis
                tick={{
                  fill: "var(--theme-text-tertiary)",
                  fontSize: 10,
                }}
                tickLine={false}
                axisLine={false}
                dx={-4}
                width={36}
                tickFormatter={(v: number) => fmt(v)}
              />

              <Tooltip
                content={<ChartTooltip />}
                cursor={{
                  stroke: "var(--theme-primary)",
                  strokeWidth: 0,
                  fill: "var(--theme-primary)",
                  fillOpacity: 0.04,
                }}
              />

              <Area
                type="monotone"
                dataKey="requests"
                name={t("usage.trend.seriesRequests")}
                stroke="var(--usage-chart-secondary)"
                strokeWidth={1.5}
                fill="url(#gradRequests)"
                dot={false}
                isAnimationActive={true}
                activeDot={{
                  r: 3,
                  fill: "var(--usage-chart-secondary)",
                  stroke: "var(--theme-bg-card)",
                  strokeWidth: 2,
                }}
              />

              <Area
                type="monotone"
                dataKey="Tokens"
                stroke="var(--theme-primary)"
                strokeWidth={2}
                fill="url(#gradTokens)"
                dot={false}
                isAnimationActive={true}
                activeDot={{
                  r: 4,
                  fill: "var(--theme-primary)",
                  stroke: "var(--theme-bg-card)",
                  strokeWidth: 2,
                }}
              />

              {/* Peak indicator dot — always visible when data exists */}
              {hasData && peakPoint.tokens > 0 && (
                <ReferenceDot
                  x={shortDate(peakPoint.date)}
                  y={peakPoint.tokens}
                  r={4}
                  fill="var(--theme-primary)"
                  stroke="var(--theme-bg-card)"
                  strokeWidth={2}
                  fillOpacity={0.8}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Summary — Mobile (3 cols) */}
      <div className="grid grid-cols-3 gap-1.5 border-t border-[var(--usage-border)] px-3 py-2.5 sm:hidden">
        <div className="flex flex-col">
          <span className="text-9 font-medium uppercase tracking-wide text-theme-text-tertiary">
            {t("usage.trend.tokens")}
          </span>
          <span className="text-13 font-bold tabular-nums text-theme-text">
            {fmt(totalTokens)}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-9 font-medium uppercase tracking-wide text-theme-text-tertiary">
            {t("usage.trend.activeDays")}
          </span>
          <span className="text-13 font-bold tabular-nums text-theme-text">
            {activeDays}/14
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-9 font-medium uppercase tracking-wide text-theme-text-tertiary">
            {t("usage.trend.peak")}
          </span>
          <span className="text-13 font-bold tabular-nums text-theme-text">
            {hasData ? shortDate(peakPoint.date) : "-"}
          </span>
        </div>
      </div>

      {/* Summary — Desktop (4 cols with icons) */}
      <div className="hidden grid-cols-4 gap-2 border-t border-[var(--usage-border)] px-4 py-3 sm:grid">
        {[
          {
            icon: Zap,
            label: t("usage.trend.tokens"),
            value: fmt(totalTokens),
          },
          {
            icon: TrendingUp,
            label: t("usage.trend.executions"),
            value: fmt(totalRequests),
          },
          {
            icon: Calendar,
            label: t("usage.trend.activeDays"),
            value: `${activeDays}/14`,
          },
          {
            icon: Flame,
            label: t("usage.trend.peak"),
            value: hasData
              ? `${shortDate(peakPoint.date)} · ${fmt(peakPoint.tokens)}`
              : "-",
          },
        ].map((item) => (
          <div key={item.label} className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <item.icon
                size={10}
                className="shrink-0 text-theme-text-tertiary"
              />
              <span className="text-10 text-theme-text-tertiary">
                {item.label}
              </span>
            </div>
            <span className="text-13 font-bold tabular-nums text-theme-text">
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
