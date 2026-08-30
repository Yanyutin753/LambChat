// 当日用量金额 → 展示货币字符串（USD 底价按应用语言换算，汇率缺失回落 USD）。
import type { UsageStats } from "../../types/usage";
import { formatCostUsd, type FxRatesDoc } from "../../utils/currency";

export interface DailyUsageAmountOpts {
  language?: string;
  rates?: FxRatesDoc | null;
}

/** 无统计数据时返回 null，调用方据此隐藏入口；有未计价请求时追加 "+"。 */
export function buildDailyUsageAmount(
  stats: UsageStats | null | undefined,
  opts: DailyUsageAmountOpts,
): string | null {
  if (!stats) return null;
  const amount = formatCostUsd(stats.total_cost_usd ?? 0, opts);
  return (stats.unpriced_requests ?? 0) > 0 ? `${amount}+` : amount;
}
