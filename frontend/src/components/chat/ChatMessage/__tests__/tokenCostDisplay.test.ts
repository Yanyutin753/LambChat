// Token 费用明细行构建（纯函数）
import type { FxRatesDoc } from "../../../utils/currency";
import type { TokenUsagePart } from "../../../types/message";
import {
  buildCostDetailRows,
  formatCostDetailRow,
  hasPricedCost,
} from "../tokenCostDisplay";

const fxRates: FxRatesDoc = {
  base: "USD",
  rates: { CNY: 7.2 },
  synced_at: "2026-08-30T00:00:00Z",
};

function usage(overrides: Partial<TokenUsagePart> = {}): TokenUsagePart {
  return {
    type: "token_usage",
    input_tokens: 1_000_000,
    output_tokens: 100_000,
    total_tokens: 1_100_000,
    cache_read_tokens: 200_000,
    cache_creation_tokens: 100_000,
    cost_usd: 0.0371,
    cost_breakdown: {
      input: 0.007,
      output: 0.03,
      cache_read: 0.0001,
      cache_write: 0,
      total: 0.0371,
    },
    cost_rates: { input: 2.5, output: 10, cache_read: 1.25, cache_write: null },
    ...overrides,
  };
}

describe("hasPricedCost", () => {
  test("true when cost_usd present", () => {
    expect(hasPricedCost(usage())).toBe(true);
  });

  test("false when unpriced or missing", () => {
    expect(hasPricedCost(usage({ cost_usd: undefined }))).toBe(false);
    expect(hasPricedCost(undefined)).toBe(false);
  });
});

describe("buildCostDetailRows", () => {
  test("billable input excludes cache tokens", () => {
    const rows = buildCostDetailRows(usage());
    const inputRow = rows.find((row) => row.key === "input");
    // 1M - 200k(cache_read) - 100k(cache_creation) = 700k
    expect(inputRow?.tokens).toBe(700_000);
    expect(inputRow?.usd).toBeCloseTo(0.007, 10);
    expect(inputRow?.ratePerMillion).toBe(2.5);
  });

  test("includes output row with tokens and rate", () => {
    const rows = buildCostDetailRows(usage());
    const outputRow = rows.find((row) => row.key === "output");
    expect(outputRow?.tokens).toBe(100_000);
    expect(outputRow?.usd).toBeCloseTo(0.03, 10);
    expect(outputRow?.ratePerMillion).toBe(10);
  });

  test("omits cache rows without tokens", () => {
    const rows = buildCostDetailRows(usage({ cache_read_tokens: 0 }));
    expect(rows.find((row) => row.key === "cache_read")).toBeUndefined();
  });

  test("missing breakdown falls back to zero component costs", () => {
    const rows = buildCostDetailRows(
      usage({ cost_breakdown: undefined, cost_rates: undefined }),
    );
    const inputRow = rows.find((row) => row.key === "input");
    expect(inputRow?.usd).toBe(0);
    expect(inputRow?.ratePerMillion).toBeNull();
  });

  test("empty usage returns no rows", () => {
    expect(buildCostDetailRows(undefined)).toEqual([]);
  });
});

describe("formatCostDetailRow", () => {
  test("renders cost and per-million rate in the i18n display currency", () => {
    const rows = buildCostDetailRows(usage());
    const input = rows.find((row) => row.key === "input");
    expect(input).toBeDefined();

    const formatted = formatCostDetailRow(input!, {
      language: "zh",
      rates: fxRates,
    });
    // 0.007 USD × 7.2 = 0.0504 CNY；2.5 USD/M × 7.2 = 18 CNY/M
    expect(formatted.cost).toBe("¥0.0504");
    expect(formatted.rate).toBe("¥18.00/M");
  });

  test("falls back to USD when fx rates are unavailable", () => {
    const rows = buildCostDetailRows(usage());
    const output = rows.find((row) => row.key === "output");
    expect(output).toBeDefined();

    // zh-CN Intl 格式化 USD 时符号为 US$（既有 formatCostUsd 行为）
    const formatted = formatCostDetailRow(output!, {
      language: "zh",
      rates: null,
    });
    expect(formatted.cost).toBe("US$0.03");
    expect(formatted.rate).toBe("US$10.00/M");
  });

  test("rate is null when the unit price is unknown", () => {
    const rows = buildCostDetailRows(
      usage({ cost_breakdown: undefined, cost_rates: undefined }),
    );
    const input = rows.find((row) => row.key === "input");
    expect(input).toBeDefined();

    const formatted = formatCostDetailRow(input!, {
      language: "en",
      rates: null,
    });
    expect(formatted.cost).toBe("$0.00");
    expect(formatted.rate).toBeNull();
  });
});
