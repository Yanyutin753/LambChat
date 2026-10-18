// 当日个人用量 → 输入框用量卡快照：金额、请求数、Token 四类占比与缓存命中率。
import type { UsageStats } from "../../types/usage";
import {
  buildDailyUsageAmount,
  type DailyUsageAmountOpts,
} from "./dailyUsageLabel";

export type TokenShareKey = "input" | "output" | "cacheWrite" | "cacheRead";

export interface TokenShareRow {
  key: TokenShareKey;
  tokens: number;
  /** 占四类 token 总量的百分比（0-100，无 token 时全为 0） */
  share: number;
}

export interface TodayUsageSnapshot {
  amount: string | null;
  requests: number;
  totalTokens: number;
  /** 缓存命中率 = 缓存读取 / 已认证包含缓存的 prompt 输入 */
  cacheHitRate: number | null;
  shares: TokenShareRow[];
  sharesKnown: boolean;
}

/**
 * Providers differ on whether input_tokens includes cache reads/writes.
 * Use the larger prompt total so cache metrics stay internally consistent.
 */
export function effectivePromptInput(
  input: number,
  cacheRead: number,
  cacheWrite: number,
): number {
  return Math.max(input, cacheRead + cacheWrite);
}

/** 正缓存率需要 inclusive input 认证；明确零读取不依赖写入量。 */
export function cacheHitRateFromTokens(
  input: number | undefined,
  cacheRead: number | undefined,
  _cacheWrite: number | undefined,
  unknownFields: readonly string[] = [],
  inputIncludesCache = false,
): number | null {
  if (
    unknownFields.some((field) =>
      ["input_tokens", "cache_read_tokens"].includes(field),
    )
  )
    return null;
  // Zero reads stay zero for every positive denominator, even when writes are unreported.
  if (
    typeof input === "number" &&
    Number.isFinite(input) &&
    input > 0 &&
    cacheRead === 0
  )
    return 0;
  if (
    !inputIncludesCache ||
    typeof input !== "number" ||
    !Number.isFinite(input) ||
    input <= 0 ||
    typeof cacheRead !== "number" ||
    !Number.isFinite(cacheRead) ||
    cacheRead < 0 ||
    cacheRead > input
  )
    return null;
  return cacheRead / input;
}

/** 无统计数据时返回 null，调用方据此隐藏入口。 */
export function buildTodayUsageSnapshot(
  stats: UsageStats | null | undefined,
  opts: DailyUsageAmountOpts,
): TodayUsageSnapshot | null {
  if (!stats) return null;

  const input = stats.total_input_tokens ?? 0;
  const output = stats.total_output_tokens ?? 0;
  const cacheWrite = stats.total_cache_creation_tokens ?? 0;
  const cacheRead = stats.total_cache_read_tokens ?? 0;
  const effectiveInput = effectivePromptInput(input, cacheRead, cacheWrite);
  const uncachedInput = Math.max(effectiveInput - cacheRead - cacheWrite, 0);
  const denominator = effectiveInput + output;

  const pct = (tokens: number) =>
    denominator > 0 ? (tokens / denominator) * 100 : 0;

  return {
    amount: buildDailyUsageAmount(stats, opts),
    requests: stats.total_requests ?? 0,
    totalTokens: stats.total_tokens ?? 0,
    sharesKnown:
      (stats.usage_unknown_requests ?? stats.cache_unknown_requests ?? 0) === 0,
    cacheHitRate:
      (stats.cache_unknown_requests ?? 0) > 0
        ? null
        : cacheHitRateFromTokens(
            input,
            cacheRead,
            cacheWrite,
            [],
            stats.cache_unknown_requests === 0,
          ),
    shares: [
      { key: "input", tokens: uncachedInput, share: pct(uncachedInput) },
      { key: "output", tokens: output, share: pct(output) },
      { key: "cacheWrite", tokens: cacheWrite, share: pct(cacheWrite) },
      { key: "cacheRead", tokens: cacheRead, share: pct(cacheRead) },
    ],
  };
}
