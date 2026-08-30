// Token 费用明细行构建：把 TokenUsagePart 的金额分解为可渲染的行数据。
import type { TokenUsagePart } from "../../../types/message";

export type CostRowKey = "input" | "output" | "cache_read" | "cache_write";

export interface CostDetailRow {
  key: CostRowKey;
  /** 该档计费 token 数 */
  tokens: number;
  /** 该档 USD 成本 */
  usd: number;
  /** 该档单价（USD / 每百万 token）；未知为 null */
  ratePerMillion: number | null;
}

/** 是否有可展示的金额（未匹配价格的模型为 false） */
export function hasPricedCost(usage: TokenUsagePart | undefined): boolean {
  return typeof usage?.cost_usd === "number";
}

/**
 * 构建费用明细行。
 * 输入行 token 数为计费口径：input_tokens - cache_read - cache_creation。
 */
export function buildCostDetailRows(usage: TokenUsagePart | undefined): CostDetailRow[] {
  if (!usage) return [];
  const cacheRead = usage.cache_read_tokens ?? 0;
  const cacheCreation = usage.cache_creation_tokens ?? 0;
  const breakdown = usage.cost_breakdown;
  const rates = usage.cost_rates;

  const rows: CostDetailRow[] = [
    {
      key: "input",
      tokens: Math.max(usage.input_tokens - cacheRead - cacheCreation, 0),
      usd: breakdown?.input ?? 0,
      ratePerMillion: rates?.input ?? null,
    },
    {
      key: "output",
      tokens: usage.output_tokens,
      usd: breakdown?.output ?? 0,
      ratePerMillion: rates?.output ?? null,
    },
  ];

  if (cacheRead > 0) {
    rows.push({
      key: "cache_read",
      tokens: cacheRead,
      usd: breakdown?.cache_read ?? 0,
      ratePerMillion: rates?.cache_read ?? null,
    });
  }
  if (cacheCreation > 0) {
    rows.push({
      key: "cache_write",
      tokens: cacheCreation,
      usd: breakdown?.cache_write ?? 0,
      ratePerMillion: rates?.cache_write ?? null,
    });
  }
  return rows;
}
