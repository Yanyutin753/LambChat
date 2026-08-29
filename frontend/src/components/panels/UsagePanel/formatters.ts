import { formatDuration } from "../../../utils/datetime";
import { formatCostUsd, type FxRatesDoc } from "../../../utils/currency";
import type { UsageDailyPoint } from "../../../types/usage";

export function fmt(n: number): string {
  if (n >= 1_000_000_000_000) return `${(n / 1_000_000_000_000).toFixed(1)}T`;
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

export function fmtDur(seconds: number): string {
  if (seconds <= 0) return "-";
  return formatDuration(seconds * 1000);
}

export function pct(value: number): string {
  if (!Number.isFinite(value)) return "0%";
  return `${Math.round(value * 100)}%`;
}

export function precise(n: number, digits = 1): string {
  if (!Number.isFinite(n)) return "0";
  return n.toFixed(digits).replace(/\.0$/, "");
}

export function shortDate(value: string): string {
  const parts = value.split("-");
  if (parts.length === 3) return `${parts[1]}/${parts[2]}`;
  return value;
}

function toDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function normalizeTrendPoints(
  points: UsageDailyPoint[],
): UsageDailyPoint[] {
  const byDate = new Map(points.map((point) => [point.date, point]));
  const sorted = [...points].sort((a, b) => a.date.localeCompare(b.date));
  const end =
    sorted.length > 0
      ? new Date(`${sorted[sorted.length - 1].date}T00:00:00`)
      : new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - 13);
  const result: UsageDailyPoint[] = [];
  for (
    let cursor = new Date(start);
    cursor <= end;
    cursor.setDate(cursor.getDate() + 1)
  ) {
    const date = toDateKey(cursor);
    result.push(
      byDate.get(date) ?? {
        date,
        requests: 0,
        tokens: 0,
        duration: 0,
        scheduled_runs: 0,
        failed_requests: 0,
        tool_calls: 0,
      },
    );
  }
  return result;
}

export interface CostFormatOpts {
  language?: string;
  rates?: FxRatesDoc | null;
}

/** 用量日志成本展示：未计价显示占位符，已计价按展示货币格式化 */
export function fmtCostUsd(
  usd: number | undefined,
  available: boolean,
  opts: CostFormatOpts,
): string {
  if (!available) return "—";
  return formatCostUsd(usd ?? 0, opts);
}
