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
  /** 缓存命中率 = 缓存读取 / (缓存读取 + 输入)，无输入面 token 时为 null */
  cacheHitRate: number | null;
  shares: TokenShareRow[];
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
  const denominator = input + output + cacheWrite + cacheRead;

  const pct = (tokens: number) =>
    denominator > 0 ? (tokens / denominator) * 100 : 0;

  const inputFacing = cacheRead + input;

  return {
    amount: buildDailyUsageAmount(stats, opts),
    requests: stats.total_requests ?? 0,
    totalTokens: stats.total_tokens ?? 0,
    cacheHitRate: inputFacing > 0 ? cacheRead / inputFacing : null,
    shares: [
      { key: "input", tokens: input, share: pct(input) },
      { key: "output", tokens: output, share: pct(output) },
      { key: "cacheWrite", tokens: cacheWrite, share: pct(cacheWrite) },
      { key: "cacheRead", tokens: cacheRead, share: pct(cacheRead) },
    ],
  };
}
