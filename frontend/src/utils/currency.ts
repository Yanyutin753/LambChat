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
