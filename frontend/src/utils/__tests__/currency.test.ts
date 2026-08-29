// USD 底层计价 → 按语言/地区换算展示货币
import {
  LOCALE_CURRENCY_MAP,
  convertUsdToCurrency,
  formatCostUsd,
  getUsdRate,
  resolveDisplayCurrency,
} from "../currency";

const rates = { base: "USD", rates: { USD: 1, CNY: 7.1, JPY: 150, KRW: 1350, RUB: 92 }, synced_at: null };

describe("resolveDisplayCurrency", () => {
  test("maps app language to local currency", () => {
    expect(resolveDisplayCurrency("zh-CN", rates)).toBe("CNY");
    expect(resolveDisplayCurrency("zh", rates)).toBe("CNY");
    expect(resolveDisplayCurrency("ja", rates)).toBe("JPY");
    expect(resolveDisplayCurrency("ko", rates)).toBe("KRW");
    expect(resolveDisplayCurrency("ru", rates)).toBe("RUB");
    expect(resolveDisplayCurrency("en-US", rates)).toBe("USD");
  });

  test("falls back to USD when rates are unavailable for the currency", () => {
    expect(resolveDisplayCurrency("zh", null)).toBe("USD");
    expect(resolveDisplayCurrency("zh", { base: "USD", rates: { USD: 1 }, synced_at: null })).toBe("USD");
  });

  test("unknown language falls back to USD", () => {
    expect(resolveDisplayCurrency("fr", rates)).toBe("USD");
    expect(resolveDisplayCurrency(undefined, rates)).toBe("USD");
  });
});

describe("getUsdRate / convertUsdToCurrency", () => {
  test("USD rate is always 1", () => {
    expect(getUsdRate("USD", null)).toBe(1);
  });

  test("converts using the rate table", () => {
    expect(convertUsdToCurrency(2, "CNY", rates)).toBeCloseTo(14.2, 10);
  });

  test("returns null when currency rate is missing", () => {
    expect(convertUsdToCurrency(2, "CNY", null)).toBeNull();
    expect(convertUsdToCurrency(2, "CNY", { base: "USD", rates: { USD: 1 }, synced_at: null })).toBeNull();
  });
});

describe("formatCostUsd", () => {
  test("formats USD with 2 decimals for normal amounts", () => {
    expect(formatCostUsd(12.3456, { language: "en" })).toBe("$12.35");
  });

  test("keeps more precision for tiny amounts", () => {
    expect(formatCostUsd(0.0123, { language: "en" })).toBe("$0.0123");
    expect(formatCostUsd(0.000123, { language: "en" })).toBe("$0.000123");
  });

  test("zero and free models still format", () => {
    expect(formatCostUsd(0, { language: "en" })).toBe("$0.00");
  });

  test("converts to local currency with symbol", () => {
    const out = formatCostUsd(0.05, { language: "zh", rates });
    expect(out).toContain("0.355");
    expect(out).toContain("¥");
  });

  test("falls back to USD when rate unavailable", () => {
    // zh locale 下 USD 显示为 US$（ICU locale 行为）
    expect(formatCostUsd(1, { language: "zh", rates: null })).toContain("1.00");
  });

  test("KRW large magnitude formats with 2 decimals", () => {
    const out = formatCostUsd(2, { language: "ko", rates });
    expect(out).toContain("2,700");
  });
});

describe("LOCALE_CURRENCY_MAP", () => {
  test("covers every supported app locale", () => {
    for (const locale of ["zh", "en", "ja", "ko", "ru"]) {
      expect(LOCALE_CURRENCY_MAP[locale]).toBeTruthy();
    }
  });
});
