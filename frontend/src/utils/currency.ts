// USD 底层计价 → 展示货币换算。
// 底层（事件、usage_logs、聚合）统一存 USD；展示时按应用语言映射本地货币，
// 汇率来自后端 /api/pricing/sync 同步的 USD 基准表；汇率不可用时回落 USD。

export interface FxRatesDoc {
  base: string;
  rates: Record<string, number>;
  synced_at: string | null;
}

/** 应用语言 → 默认展示货币 */
export const LOCALE_CURRENCY_MAP: Record<string, string> = {
  zh: "CNY",
  en: "USD",
  ja: "JPY",
  ko: "KRW",
  ru: "RUB",
};

const LOCALE_TAG: Record<string, string> = {
  zh: "zh-CN",
  en: "en-US",
  ja: "ja-JP",
  ko: "ko-KR",
  ru: "ru-RU",
};

export function resolveDisplayCurrency(
  language: string | undefined,
  rates: FxRatesDoc | null,
): string {
  const primary = (language || "").toLowerCase().split(/[-_]/)[0];
  const currency = LOCALE_CURRENCY_MAP[primary] || "USD";
  if (currency === "USD") return "USD";
  const rate = rates?.rates?.[currency];
  return typeof rate === "number" && rate > 0 ? currency : "USD";
}

export function getUsdRate(
  currency: string,
  rates: FxRatesDoc | null,
): number | null {
  if (currency === "USD") return 1;
  const rate = rates?.rates?.[currency];
  return typeof rate === "number" && rate > 0 ? rate : null;
}

export function convertUsdToCurrency(
  usd: number,
  currency: string,
  rates: FxRatesDoc | null,
): number | null {
  const rate = getUsdRate(currency, rates);
  if (rate === null) return null;
  return usd * rate;
}

function localeTag(language: string | undefined): string {
  const primary = (language || "").toLowerCase().split(/[-_]/)[0];
  return LOCALE_TAG[primary] || "en-US";
}

function decimalsFor(value: number): { min: number; max: number } {
  const abs = Math.abs(value);
  // 常规金额两位；不足 1 的金额保留到 6 位并去尾零，避免小金额失真
  if (abs >= 1 || abs === 0) return { min: 2, max: 2 };
  return { min: 1, max: 6 };
}

/** USD 金额 → 本地货币格式化字符串；无法换算时回落 USD。 */
export function formatCostUsd(
  usd: number,
  opts: {
    language?: string;
    rates?: FxRatesDoc | null;
    /** 小数位上限（换算后应用）；手机端窄格子用它截短小金额精度 */
    maxDecimals?: number;
    /** 固定小数位（换算后应用）。 */
    decimals?: number;
  },
): string {
  const language = opts.language;
  const currency = resolveDisplayCurrency(language, opts.rates ?? null);
  const converted = convertUsdToCurrency(usd, currency, opts.rates ?? null);
  const value = converted ?? usd;
  const finalCurrency = converted === null ? "USD" : currency;
  let { min, max } = decimalsFor(value);
  if (typeof opts.maxDecimals === "number") {
    max = Math.min(max, opts.maxDecimals);
    min = Math.min(min, max);
  }
  if (typeof opts.decimals === "number") min = max = opts.decimals;
  try {
    return new Intl.NumberFormat(localeTag(language), {
      style: "currency",
      currency: finalCurrency,
      minimumFractionDigits: min,
      maximumFractionDigits: max,
    }).format(value);
  } catch {
    return `$${value.toFixed(max)}`;
  }
}

export interface UsageCostFormatOpts {
  pricedRequests?: number;
  unpricedRequests?: number;
  partialCostUsd?: number | null;
  partialRequests?: number;
  estimatedCostUsd?: number | null;
  estimatedRequests?: number;
  language?: string;
  rates?: FxRatesDoc | null;
  maxDecimals?: number;
  decimals?: number;
}

export function isCostAmount(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

/** Confirmed and independently calculated amounts exclude historical estimates. */
export function formatUsageCost(
  usd: number | null | undefined,
  available: boolean,
  opts: UsageCostFormatOpts,
): string {
  const unknown = (opts.unpricedRequests ?? 0) > 0;
  const confirmed =
    available === true &&
    isCostAmount(usd) &&
    !(unknown && opts.pricedRequests === 0);
  const partial =
    isCostAmount(opts.partialCostUsd) &&
    (opts.partialRequests === undefined || opts.partialRequests > 0);
  if (confirmed || partial) {
    const amount = (confirmed ? usd : 0) + (partial ? opts.partialCostUsd! : 0);
    return `${formatCostUsd(amount, opts)}${unknown || partial ? "+" : ""}`;
  }
  const estimated =
    isCostAmount(opts.estimatedCostUsd) &&
    (opts.estimatedRequests === undefined || opts.estimatedRequests > 0);
  return estimated ? `≈${formatCostUsd(opts.estimatedCostUsd!, opts)}` : "—";
}

/** Pass aggregate or per-log certainty fields into the shared formatter. */
export function usageCostOptions(data: {
  priced_requests?: number;
  unpriced_requests?: number;
  partial_cost_usd?: number | null;
  partial_requests?: number;
  estimated_cost_usd?: number | null;
  estimated_requests?: number;
}): UsageCostFormatOpts {
  return {
    pricedRequests: data.priced_requests,
    unpricedRequests: data.unpriced_requests,
    partialCostUsd: data.partial_cost_usd,
    partialRequests: data.partial_requests,
    estimatedCostUsd: data.estimated_cost_usd,
    estimatedRequests: data.estimated_requests,
  };
}

export function historicalEstimateHint(
  opts: UsageCostFormatOpts,
  label: string,
): string | undefined {
  if (!isCostAmount(opts.estimatedCostUsd) || opts.estimatedRequests === 0)
    return undefined;
  return `${label}: ≈${formatCostUsd(opts.estimatedCostUsd, opts)}`;
}
