import { reportedTokenCount } from "../../../utils/usageTokens";
import { formatDuration } from "../../../utils/datetime";
import {
  formatUsageCost,
  type UsageCostFormatOpts,
} from "../../../utils/currency";
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

export type UsageStatusKind = "ok" | "cancelled" | "running" | "error";

/** 用量记录状态：运行中 / 完成 / 用户取消 / 失败（未知按失败展示）。 */
export function usageStatusKind(status: string): UsageStatusKind {
  if (status === "running") return "running";
  if (status === "completed") return "ok";
  if (status === "cancelled") return "cancelled";
  return "error";
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
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

export type CostFormatOpts = UsageCostFormatOpts;

/** Shared certainty-aware cost display for usage logs and aggregates. */
export function fmtCostUsd(
  usd: number | null | undefined,
  available: boolean,
  opts: CostFormatOpts,
): string {
  return formatUsageCost(usd, available, opts);
}

/** A missing call does not erase a positive subtotal reported by other calls. */
export function reportedAggregateCount(
  value: unknown,
  field: string,
  unknownFields?: readonly string[] | null,
): number | null {
  return reportedTokenCount(
    value,
    field,
    typeof value === "number" && value > 0 ? [] : unknownFields,
  );
}

export function fmtUsageCount(
  value: unknown,
  field: string,
  unknownFields?: readonly string[] | null,
): string {
  const count = reportedAggregateCount(value, field, unknownFields);
  return count === null ? "—" : fmt(count);
}

/** Aggregate cache share uses the counters available in the selected window. */
export function aggregateCacheShare(
  input?: number | null,
  read?: number | null,
  write?: number | null,
): number {
  const denominator = Math.max(input ?? 0, (read ?? 0) + (write ?? 0));
  return denominator > 0 ? Math.min((read ?? 0) / denominator, 1) : 0;
}
