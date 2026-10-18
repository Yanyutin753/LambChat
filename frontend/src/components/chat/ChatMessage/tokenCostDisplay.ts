import { reportedTokenCount } from "../../../utils/usageTokens";
// Token 费用明细行构建：把 TokenUsagePart 的金额分解为可渲染的行数据。
import type { TokenUsagePart } from "../../../types/message";
import type { UsageLog } from "../../../types/usage";
import {
  formatCostUsd,
  formatUsageCost,
  isCostAmount,
  type FxRatesDoc,
} from "../../../utils/currency";

export type CostRowKey = "input" | "output" | "cache_read" | "cache_write";

export function formatUsageTokenCount(
  usage: TokenUsagePart | UsageLog,
  field:
    | "input_tokens"
    | "output_tokens"
    | "total_tokens"
    | "cache_read_tokens"
    | "cache_creation_tokens",
  formatCount: (value: number) => string = (value) => value.toLocaleString(),
): string {
  const value = reportedTokenCount(
    usage[field],
    field,
    usage.unknown_usage_fields,
  );
  if (
    value === null ||
    (usage.usage_incomplete === true && !usage.unknown_usage_fields?.length)
  ) {
    return "—";
  }
  return formatCount(value);
}

export interface CostDetailRow {
  key: CostRowKey;
  /** 该档计费 token 数 */
  tokens: number;
  /** 该档 USD 成本 */
  usd: number | null;
  /** 该档单价（USD / 每百万 token）；未知为 null */
  ratePerMillion: number | null;
}

function cacheWritesIncludedInInput(usage: TokenUsagePart): boolean {
  const rates = usage.cost_rates;
  return (
    rates?.cache_write_included === true &&
    (rates.cache_write == null || rates.cache_write === 0)
  );
}

/** Financial completeness can be certified independently of write token counts. */
export function hasPricedCost(usage: TokenUsagePart | undefined): boolean {
  if (usage?.cost_source === "provider_settlement") {
    return (
      usage.cost_complete === true &&
      Number.isSafeInteger(usage.cost_units) &&
      usage.cost_units! >= 0 &&
      isCostAmount(usage.cost_usd) &&
      usage.cost_usd === usage.cost_units! / 1_000_000_000
    );
  }
  if (
    !usage ||
    !isCostAmount(usage.cost_usd) ||
    usage.input_includes_cache !== true
  )
    return false;
  const knownCount = (
    field:
      | "input_tokens"
      | "output_tokens"
      | "cache_read_tokens"
      | "cache_creation_tokens",
  ) =>
    reportedTokenCount(usage[field], field, usage.unknown_usage_fields) !==
      null && Number.isInteger(usage[field]);
  if (
    !knownCount("input_tokens") ||
    !knownCount("output_tokens") ||
    !knownCount("cache_read_tokens")
  )
    return false;
  const cacheRead = usage.cache_read_tokens!;
  const includedWrites = cacheWritesIncludedInInput(usage);
  if (
    cacheRead > usage.input_tokens ||
    (usage.cost_rates?.cache_write_included === true && !includedWrites)
  )
    return false;
  if (usage.cost_complete !== true && usage.usage_incomplete !== false)
    return false;
  const writeKnown = knownCount("cache_creation_tokens");
  if (!writeKnown && !(usage.cost_complete === true && includedWrites))
    return false;
  if (
    writeKnown &&
    cacheRead + usage.cache_creation_tokens! > usage.input_tokens
  )
    return false;
  const rates = usage.cost_rates;
  return (
    !rates ||
    !(
      (cacheRead > 0 && rates.cache_read == null) ||
      (!includedWrites &&
        (usage.cache_creation_tokens ?? 0) > 0 &&
        rates.cache_write == null)
    )
  );
}

/** Historical messages retain their original estimate without certifying it. */
export function tokenUsageEstimatedCost(
  usage: TokenUsagePart | undefined,
): number | undefined {
  if (!usage) return undefined;
  if (isCostAmount(usage.estimated_cost_usd)) return usage.estimated_cost_usd;
  return !hasPricedCost(usage) && isCostAmount(usage.cost_usd)
    ? usage.cost_usd
    : undefined;
}

export function formatTokenUsageCost(
  usage: TokenUsagePart | undefined,
  opts: FormatCostRowOpts,
): string {
  return formatUsageCost(usage?.cost_usd, hasPricedCost(usage), {
    ...opts,
    partialCostUsd: usage?.partial_cost_usd,
    estimatedCostUsd: tokenUsageEstimatedCost(usage),
  });
}

/**
 * 构建费用明细行。
 * 输入行按计费策略扣除缓存；创建已包含在普通输入价时仅扣除读取。
 */
export function buildCostDetailRows(
  usage: TokenUsagePart | undefined,
): CostDetailRow[] {
  if (
    !usage ||
    (usage.usage_incomplete === true &&
      !usage.partial_cost_breakdown &&
      !hasPricedCost(usage))
  )
    return [];
  const cacheRead = usage.cache_read_tokens ?? 0;
  const cacheCreation = usage.cache_creation_tokens ?? 0;
  const breakdown = usage.partial_cost_breakdown ?? usage.cost_breakdown;
  const rates = usage.cost_rates;
  const includedWrites = cacheWritesIncludedInInput(usage);

  const knownCount = (
    field:
      | "input_tokens"
      | "output_tokens"
      | "cache_read_tokens"
      | "cache_creation_tokens",
  ) =>
    isCostAmount(usage[field]) && !usage.unknown_usage_fields?.includes(field);
  const rows: CostDetailRow[] = [];
  if (
    knownCount("input_tokens") &&
    knownCount("cache_read_tokens") &&
    (knownCount("cache_creation_tokens") ||
      (includedWrites &&
        (hasPricedCost(usage) || isCostAmount(breakdown?.input))))
  ) {
    rows.push({
      key: "input",
      tokens: Math.max(
        usage.input_tokens - cacheRead - (includedWrites ? 0 : cacheCreation),
        0,
      ),
      usd: breakdown?.input ?? null,
      ratePerMillion: rates?.input ?? null,
    });
  }
  if (knownCount("output_tokens")) {
    rows.push({
      key: "output",
      tokens: usage.output_tokens,
      usd: breakdown?.output ?? null,
      ratePerMillion: rates?.output ?? null,
    });
  }

  if (knownCount("cache_read_tokens") && cacheRead > 0) {
    rows.push({
      key: "cache_read",
      tokens: cacheRead,
      usd: breakdown?.cache_read ?? null,
      ratePerMillion: rates?.cache_read ?? null,
    });
  }
  if (
    !includedWrites &&
    knownCount("cache_creation_tokens") &&
    cacheCreation > 0
  ) {
    rows.push({
      key: "cache_write",
      tokens: cacheCreation,
      usd: breakdown?.cache_write ?? null,
      ratePerMillion: rates?.cache_write ?? null,
    });
  }
  return rows;
}

export interface FormatCostRowOpts {
  language?: string;
  rates?: FxRatesDoc | null;
}

/** 明细行金额与单价格式化为 i18n 对应货币（USD 底价换算，汇率缺失回落 USD） */
export function formatCostDetailRow(
  row: CostDetailRow,
  opts: FormatCostRowOpts,
): { cost: string; rate: string | null } {
  return {
    cost: row.usd === null ? "—" : formatCostUsd(row.usd, opts),
    rate:
      row.ratePerMillion === null
        ? null
        : `${formatCostUsd(row.ratePerMillion, opts)}/M`,
  };
}
