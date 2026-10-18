// 当日用量金额 → 展示货币字符串（USD 底价按应用语言换算，汇率缺失回落 USD）。
import type { UsageStats } from "../../types/usage";
import { formatCostUsd, type FxRatesDoc } from "../../utils/currency";

export interface DailyUsageAmountOpts {
  language?: string;
  rates?: FxRatesDoc | null;
}

/** 无统计时隐藏；全部未计价时显示未知，部分已计价时保留已知金额并追加 "+"。 */
export function buildDailyUsageAmount(
  stats: UsageStats | null | undefined,
  opts: DailyUsageAmountOpts,
): string | null {
  if (!stats) return null;
  const unpriced = stats.unpriced_requests ?? 0;
  const priced =
    stats.priced_requests ?? Math.max(stats.total_requests - unpriced, 0);
  if (
    typeof stats.total_cost_usd !== "number" ||
    !Number.isFinite(stats.total_cost_usd) ||
    (unpriced > 0 && priced === 0)
  )
    return "—";
  const amount = formatCostUsd(stats.total_cost_usd, { ...opts, decimals: 3 });
  return (stats.unpriced_requests ?? 0) > 0 ? `${amount}+` : amount;
}
