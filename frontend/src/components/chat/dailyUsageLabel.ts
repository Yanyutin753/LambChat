// 当日用量金额 → 展示货币字符串（USD 底价按应用语言换算，汇率缺失回落 USD）。
import type { UsageStats } from "../../types/usage";
import {
  formatUsageCost,
  usageCostOptions,
  type FxRatesDoc,
} from "../../utils/currency";

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
  return formatUsageCost(stats.total_cost_usd, true, {
    ...opts,
    ...usageCostOptions(stats),
    pricedRequests:
      stats.priced_requests ??
      Math.max(stats.total_requests - (stats.unpriced_requests ?? 0), 0),
    decimals: 3,
  });
}
