import { useMemo } from "react";
import { LineChart, TrendingUp, Zap, Calendar, Flame } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { UsageDailyPoint } from "../../../types/usage";
import { fmt, fmtDur, normalizeTrendPoints, shortDate } from "./formatters";

type MiniTrendChartPoint = {
  date: string;
  label: string;
  tokens: number;
  requests: number;
  x: number;
  tokenY: number;
  requestY: number;
};

function chartPath(
  points: MiniTrendChartPoint[],
  key: "tokenY" | "requestY",
) {
  return points
    .map((point, index) =>
      `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point[
        key
      ].toFixed(1)}`,
    )
    .join(" ");
}

function chartAreaPath(
  points: MiniTrendChartPoint[],
  key: "tokenY" | "requestY",
) {
  if (points.length === 0) return "";
  const line = chartPath(points, key);
  const first = points[0];
  const last = points[points.length - 1];
  return `${line} L ${last.x.toFixed(1)} 160 L ${first.x.toFixed(1)} 160 Z`;
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
  const peakIdx = visible.length
    ? visible.reduce(
        (best, p, i) => (p.tokens > visible[best].tokens ? i : best),
        0,
      )
    : 0;
  const peakPoint = visible[peakIdx];

  const chartPoints = useMemo<MiniTrendChartPoint[]>(() => {
    const width = 320;
    const height = 160;
    const maxValue = Math.max(
      1,
      ...visible.map((point) => Math.max(point.tokens, point.requests)),
    );
    const step = visible.length > 1 ? width / (visible.length - 1) : 0;
    return visible.map((point, index) => {
      const x = visible.length > 1 ? index * step : width / 2;
      return {
        date: point.date,
        label: shortDate(point.date),
        tokens: point.tokens,
        requests: point.requests,
        x,
        tokenY: height - (point.tokens / maxValue) * height,
        requestY: height - (point.requests / maxValue) * height,
      };
    });
  }, [visible]);
  const tokenPath = chartPath(chartPoints, "tokenY");
  const requestPath = chartPath(chartPoints, "requestY");
  const tokenAreaPath = chartAreaPath(chartPoints, "tokenY");
  const requestAreaPath = chartAreaPath(chartPoints, "requestY");

  return (
    <div className="usage-surface usage-chart-card overflow-hidden rounded-xl">
      <div className="flex items-start justify-between gap-3 border-b border-[var(--usage-border)] px-4 pt-4 pb-3.5 sm:px-5">
        <div className="flex items-center gap-2.5">
          <div className="usage-icon flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--usage-icon-bg)] text-[var(--theme-primary)] sm:h-9 sm:w-9">
            <LineChart size={15} strokeWidth={2} />
          </div>
          <div>
            <h3 className="text-[13px] font-bold tracking-tight text-theme-text sm:text-sm">
              {t("usage.trend.title")}
            </h3>
            <p className="text-[10px] text-theme-text-tertiary sm:text-[11px]">
              {t("usage.trend.subtitle")}
            </p>
          </div>
        </div>
        <div className="hidden flex-wrap justify-end gap-1.5 text-[10px] sm:flex">
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

      <div className="bg-[var(--usage-inset-bg)] px-1 py-2 sm:px-2 sm:py-3">
        {!hasData ? (
          <div className="usage-empty-state flex h-[180px] flex-col items-center justify-center gap-2 text-theme-text-tertiary sm:h-[220px]">
            <LineChart size={24} className="opacity-20" />
            <span className="text-xs">{t("usage.trend.empty")}</span>
          </div>
        ) : (
          <div className="h-[180px] px-3 py-2 sm:h-[220px]">
            <svg
              viewBox="0 0 360 190"
              role="img"
              aria-label={t("usage.trend.title")}
              className="h-full w-full overflow-visible"
              preserveAspectRatio="none"
            >
              <defs>
                <linearGradient
                  id="usage-mini-trend-tokens"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor="var(--theme-primary)"
                    stopOpacity="0.3"
                  />
                  <stop
                    offset="95%"
                    stopColor="var(--theme-primary)"
                    stopOpacity="0"
                  />
                </linearGradient>
                <linearGradient
                  id="usage-mini-trend-requests"
                  x1="0"
                  y1="0"
                  x2="0"
                  y2="1"
                >
                  <stop
                    offset="0%"
                    stopColor="var(--usage-chart-secondary)"
                    stopOpacity="0.2"
                  />
                  <stop
                    offset="95%"
                    stopColor="var(--usage-chart-secondary)"
                    stopOpacity="0"
                  />
                </linearGradient>
              </defs>
              {[0, 40, 80, 120, 160].map((y) => (
                <line
                  key={y}
                  x1="24"
                  x2="344"
                  y1={8 + y}
                  y2={8 + y}
                  stroke="var(--usage-border)"
                  strokeDasharray="3 4"
                  opacity="0.5"
                />
              ))}
              <g transform="translate(24 8)">
                <path d={requestAreaPath} fill="url(#usage-mini-trend-requests)" />
                <path d={tokenAreaPath} fill="url(#usage-mini-trend-tokens)" />
                <path
                  d={requestPath}
                  fill="none"
                  stroke="var(--usage-chart-secondary)"
                  strokeWidth="2"
                  vectorEffect="non-scaling-stroke"
                />
                <path
                  d={tokenPath}
                  fill="none"
                  stroke="var(--theme-primary)"
                  strokeWidth="2.5"
                  vectorEffect="non-scaling-stroke"
                />
                {chartPoints.map((point) => (
                  <circle
                    key={point.date}
                    cx={point.x}
                    cy={point.tokenY}
                    r="3"
                    fill="var(--theme-primary)"
                    opacity="0.7"
                  >
                    <title>{`${point.label}: ${fmt(point.tokens)} ${t(
                      "usage.trend.tokens",
                    )}, ${fmt(point.requests)} ${t(
                      "usage.trend.seriesRequests",
                    )}`}</title>
                  </circle>
                ))}
                {peakPoint && peakPoint.tokens > 0 && (
                  <circle
                    cx={chartPoints[peakIdx]?.x ?? 0}
                    cy={chartPoints[peakIdx]?.tokenY ?? 0}
                    r="5"
                    fill="var(--theme-primary)"
                    stroke="var(--theme-bg-card)"
                    strokeWidth="2"
                  />
                )}
              </g>
              <text
                x="24"
                y="186"
                fill="var(--theme-text-tertiary)"
                fontSize="10"
              >
                {chartPoints[0]?.label ?? ""}
              </text>
              <text
                x="344"
                y="186"
                textAnchor="end"
                fill="var(--theme-text-tertiary)"
                fontSize="10"
              >
                {chartPoints[chartPoints.length - 1]?.label ?? ""}
              </text>
            </svg>
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-1.5 border-t border-[var(--usage-border)] px-3 py-2.5 sm:hidden">
        <div className="flex flex-col">
          <span className="text-[9px] font-medium uppercase tracking-wide text-theme-text-tertiary">
            {t("usage.trend.tokens")}
          </span>
          <span className="text-[13px] font-bold tabular-nums text-theme-text">
            {fmt(totalTokens)}
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[9px] font-medium uppercase tracking-wide text-theme-text-tertiary">
            {t("usage.trend.activeDays")}
          </span>
          <span className="text-[13px] font-bold tabular-nums text-theme-text">
            {activeDays}/14
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-[9px] font-medium uppercase tracking-wide text-theme-text-tertiary">
            {t("usage.trend.peak")}
          </span>
          <span className="text-[13px] font-bold tabular-nums text-theme-text">
            {peakPoint ? shortDate(peakPoint.date) : "-"}
          </span>
        </div>
      </div>

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
            value: peakPoint
              ? `${shortDate(peakPoint.date)} / ${fmt(peakPoint.tokens)}`
              : "-",
          },
        ].map((item) => (
          <div key={item.label} className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <item.icon
                size={10}
                className="shrink-0 text-theme-text-tertiary"
              />
              <span className="text-[10px] text-theme-text-tertiary">
                {item.label}
              </span>
            </div>
            <span className="text-[13px] font-bold tabular-nums text-theme-text">
              {item.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
