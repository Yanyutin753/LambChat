import { buildDailyUsageAmount } from "../dailyUsageLabel";
import type { UsageStats } from "../../../types/usage";

function stats(overrides: Partial<UsageStats> = {}): UsageStats {
  return {
    total_requests: 3,
    total_input_tokens: 100,
    total_output_tokens: 50,
    total_tokens: 150,
    total_cache_creation_tokens: 0,
    total_cache_read_tokens: 0,
    total_cost_usd: 0.5,
    total_duration: 12,
    ...overrides,
  };
}

const cnyRates = {
  base: "USD",
  rates: { CNY: 7.2 },
  synced_at: "2026-08-30T00:00:00Z",
};

test("returns null when stats are unavailable so the pill stays hidden", () => {
  expect(
    buildDailyUsageAmount(null, { language: "zh", rates: cnyRates }),
  ).toBeNull();
  expect(
    buildDailyUsageAmount(undefined, { language: "zh", rates: cnyRates }),
  ).toBeNull();
});

test("converts today's USD cost into the display currency for zh", () => {
  expect(
    buildDailyUsageAmount(stats(), { language: "zh", rates: cnyRates }),
  ).toBe("¥3.600");
});

test("falls back to USD when fx rates are unavailable", () => {
  expect(
    buildDailyUsageAmount(stats({ total_cost_usd: 1.25 }), {
      language: "zh",
      rates: null,
    }),
  ).toBe("US$1.250");
});

test("appends a plus suffix when some requests are unpriced", () => {
  expect(
    buildDailyUsageAmount(stats({ unpriced_requests: 2 }), {
      language: "zh",
      rates: cnyRates,
    }),
  ).toBe("¥3.600+");
});

test("rounds sub-unit amounts to three decimal places", () => {
  expect(
    buildDailyUsageAmount(stats({ total_cost_usd: 0.000123 }), {
      language: "en",
    }),
  ).toBe("$0.000");
});

test("rounds the converted amount to three decimals before the plus suffix", () => {
  expect(
    buildDailyUsageAmount(
      stats({ total_cost_usd: 0.53208 / 7.2, unpriced_requests: 1 }),
      { language: "zh", rates: cnyRates },
    ),
  ).toBe("¥0.532+");
});
