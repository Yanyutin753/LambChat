import type { TFunction } from "i18next";

// ── Parse ──────────────────────────────────────────────

type TimeInput = string | number | Date;

function toDate(input: TimeInput): Date {
  if (input instanceof Date) return input;
  if (typeof input === "number") return new Date(input);
  const s = input.trim();
  if (s.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(s)) {
    return new Date(s);
  }
  return new Date(s + "Z");
}

export { toDate as parseDate };
export type { TimeInput };

// ── Display formatters ─────────────────────────────────

export function formatDateTime(input: TimeInput): string {
  return toDate(input).toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatDate(input: TimeInput): string {
  return toDate(input).toLocaleDateString();
}

export function formatTime(input: TimeInput): string {
  return toDate(input).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDateTimeShort(input: TimeInput): string {
  return toDate(input).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ── Relative time ──────────────────────────────────────

export function formatTimeAgo(t: TFunction, input: TimeInput): string {
  const diffMs = Date.now() - toDate(input).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return t("common.timeAgo.justNow");
  if (diffMin < 60) return t("common.timeAgo.minutesAgo", { count: diffMin });
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return t("common.timeAgo.hoursAgo", { count: diffHr });
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 30) return t("common.timeAgo.daysAgo", { count: diffDay });
  return t("common.timeAgo.monthsAgo", {
    count: Math.floor(diffDay / 30),
  });
}

export function formatRelativeDate(
  t: TFunction,
  input: TimeInput | null,
): string {
  if (!input) return "";
  const d = toDate(input);
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (diffDays === 0)
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (diffDays === 1) return t("common.timeAgo.daysAgo", { count: 1 });
  if (diffDays < 7) return t("common.timeAgo.daysAgo", { count: diffDays });
  if (diffDays < 30)
    return t("common.timeWeeksAgo", { count: Math.floor(diffDays / 7) });
  return t("common.timeMonthsAgo", { count: Math.floor(diffDays / 30) });
}

// ── Duration ──────────────────────────────────────────

export function formatDuration(ms: number): string {
  if (ms < 0) ms = 0;
  const totalSec = ms / 1000;
  const h = Math.floor(totalSec / 3600);
  const remainder = totalSec - h * 3600;
  const m = Math.floor(remainder / 60);
  const s = remainder - m * 60;

  if (h > 0) return `${h}h ${m}m ${Math.round(s)}s`;
  if (m > 0) return `${m}m ${Math.round(s)}s`;
  // Sub-second: show one decimal; omit 0s entirely
  if (totalSec < 1 && totalSec > 0) return `${Math.round(totalSec * 10) / 10}s`;
  if (totalSec === 0) return "";
  return `${Math.round(s)}s`;
}

// ── Comparison helpers ─────────────────────────────────

export function getTimeMs(input: TimeInput): number {
  return toDate(input).getTime();
}

/** 同一天本地 0 点（"今日"按自然日而非滚动 24 小时计算时使用） */
export function startOfLocalDay(now: Date): Date {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}
