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
  /** 缓存命中率 = 缓存读取 / 有效 prompt 输入（兼容 provider 两种口径） */
  cacheHitRate: number | null;
  shares: TokenShareRow[];
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

/** 缓存命中率（0-1）：分母为有效 prompt 输入并 clamp ≤1；无 token 返回 null。 */
export function cacheHitRateFromTokens(
  input: number,
  cacheRead: number,
  cacheWrite: number,
): number | null {
  const effectiveInput = effectivePromptInput(input, cacheRead, cacheWrite);
  if (effectiveInput <= 0) return null;
  return Math.min(cacheRead / effectiveInput, 1);
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
    cacheHitRate: cacheHitRateFromTokens(input, cacheRead, cacheWrite),
    shares: [
      { key: "input", tokens: uncachedInput, share: pct(uncachedInput) },
      { key: "output", tokens: output, share: pct(output) },
      { key: "cacheWrite", tokens: cacheWrite, share: pct(cacheWrite) },
      { key: "cacheRead", tokens: cacheRead, share: pct(cacheRead) },
    ],
  };
}
