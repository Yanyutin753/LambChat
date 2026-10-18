// Token 费用明细行构建（纯函数）
import type { FxRatesDoc } from "../../../utils/currency";
import type { TokenUsagePart } from "../../../types/message";
import {
  buildCostDetailRows,
  formatCostDetailRow,
  hasPricedCost,
  formatTokenUsageCost,
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
    usage_incomplete: false,
    input_includes_cache: true,
    cost_usd: 0.0371,
    cost_breakdown: {
      input: 0.007,
      output: 0.03,
      cache_read: 0.0001,
      cache_write: 0,
      total: 0.0371,
    },
    cost_rates: { input: 2.5, output: 10, cache_read: 1.25, cache_write: 0 },
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

  test("incomplete accounting cannot turn an old estimate into a complete cost", () => {
    expect(hasPricedCost(usage({ usage_incomplete: true }))).toBe(false);
  });

  test("missing cache metrics are unknown even with a stored legacy estimate", () => {
    expect(hasPricedCost(usage({ cache_creation_tokens: undefined }))).toBe(
      false,
    );
  });

  test("positive cache usage with an explicitly unknown price is not free", () => {
    expect(
      hasPricedCost(
        usage({
          cost_rates: {
            input: 2.5,
            output: 10,
            cache_read: null,
            cache_write: 0,
          },
        }),
      ),
    ).toBe(false);
  });

  test("legacy counters without completeness evidence are not a certified cost", () => {
    expect(hasPricedCost(usage({ usage_incomplete: undefined }))).toBe(false);
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

  test("missing breakdown preserves unknown component costs", () => {
    const rows = buildCostDetailRows(
      usage({ cost_breakdown: undefined, cost_rates: undefined }),
    );
    const inputRow = rows.find((row) => row.key === "input");
    expect(inputRow?.usd).toBeNull();
    expect(inputRow?.ratePerMillion).toBeNull();
  });

  test("empty usage returns no rows", () => {
    expect(buildCostDetailRows(undefined)).toEqual([]);
    expect(buildCostDetailRows(usage({ usage_incomplete: true }))).toEqual([]);
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
    expect(formatted.cost).toBe("—");
    expect(formatted.rate).toBeNull();
  });
});

test("an old cost estimate needs an inclusive input certificate", () => {
  expect(hasPricedCost(usage({ input_includes_cache: undefined }))).toBe(false);
  expect(hasPricedCost(usage({ input_includes_cache: false }))).toBe(false);
});

describe("formatTokenUsageCost", () => {
  test("old uncertified chat cost remains visible as a historical estimate", () => {
    const old = usage({
      usage_incomplete: undefined,
      input_includes_cache: undefined,
    });
    expect(hasPricedCost(old)).toBe(false);
    expect(formatTokenUsageCost(old, { language: "en" })).toBe("≈$0.0371");
  });
  test("partial cost is visible even when only a zero amount is calculable", () => {
    expect(
      formatTokenUsageCost(
        usage({
          cost_usd: undefined,
          usage_incomplete: true,
          partial_cost_usd: 0,
        }),
        { language: "en" },
      ),
    ).toBe("$0.00+");
  });
  test("fully unknown chat cost stays unknown", () => {
    expect(
      formatTokenUsageCost(usage({ cost_usd: undefined }), { language: "en" }),
    ).toBe("—");
  });
});

test("numeric certificates cannot certify an old estimate", () => {
  const legacy = usage({ input_includes_cache: 1 as unknown as boolean });
  expect(hasPricedCost(legacy)).toBe(false);
  expect(formatTokenUsageCost(legacy, { language: "en" })).toBe("≈$0.0371");
});

test("partial rows omit ordinary input when a cache counter is unknown", () => {
  const rows = buildCostDetailRows(
    usage({
      usage_incomplete: true,
      unknown_usage_fields: ["cache_creation_tokens"],
      cache_creation_tokens: undefined,
      partial_cost_breakdown: { output: 0.03, cache_read: 0.0001 },
    }),
  );
  expect(rows.find((row) => row.key === "input")).toBeUndefined();
  expect(rows.find((row) => row.key === "output")?.tokens).toBe(100_000);
  expect(rows.find((row) => row.key === "cache_read")?.tokens).toBe(200_000);
});

test("partial rows omit an unknown output counter rather than inventing zero", () => {
  const rows = buildCostDetailRows(
    usage({
      usage_incomplete: true,
      unknown_usage_fields: ["output_tokens"],
      output_tokens: 0,
      partial_cost_breakdown: { input: 0.007, cache_read: 0.0001 },
    }),
  );
  expect(rows.find((row) => row.key === "output")).toBeUndefined();
  expect(rows.find((row) => row.key === "input")?.tokens).toBe(700_000);
});

function noSeparateWriteUsage(
  overrides: Partial<TokenUsagePart> = {},
): TokenUsagePart {
  return usage({
    input_tokens: 12822,
    output_tokens: 86,
    total_tokens: 12908,
    cache_read_tokens: 10880,
    cache_creation_tokens: undefined,
    usage_incomplete: true,
    unknown_usage_fields: ["cache_creation_tokens"],
    cost_complete: true,
    cost_usd: 0.005926,
    cost_rates: {
      input: 1.4,
      output: 4.4,
      cache_read: 0.26,
      cache_write: 0,
      cache_write_included: true,
    },
    cost_breakdown: {
      input: 0.0027188,
      output: 0.0003784,
      cache_read: 0.0028288,
      cache_write: 0,
      total: 0.005926,
    },
    ...overrides,
  });
}

test("financial certification prices providers with no separate write charge without inventing write tokens", () => {
  const value = noSeparateWriteUsage();
  expect(hasPricedCost(value)).toBe(true);
  expect(formatTokenUsageCost(value, { language: "en" })).toBe("$0.005926");
  expect(value.cache_creation_tokens).toBeUndefined();
  expect(value.usage_incomplete).toBe(true);
  expect(
    buildCostDetailRows(value).find((row) => row.key === "input")?.tokens,
  ).toBe(1942);
  const measuredWrite = noSeparateWriteUsage({
    cache_creation_tokens: 100,
    unknown_usage_fields: [],
    usage_incomplete: false,
  });
  expect(
    buildCostDetailRows(measuredWrite).find((row) => row.key === "input")
      ?.tokens,
  ).toBe(1942);
});

test("financial certification must be literal and requires valid billable input output and reads", () => {
  expect(
    hasPricedCost(
      noSeparateWriteUsage({ cost_complete: 1 as unknown as boolean }),
    ),
  ).toBe(false);
  for (const field of [
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
  ] as const) {
    expect(
      hasPricedCost(
        noSeparateWriteUsage({
          unknown_usage_fields: ["cache_creation_tokens", field],
        }),
      ),
    ).toBe(false);
    expect(hasPricedCost(noSeparateWriteUsage({ [field]: Number.NaN }))).toBe(
      false,
    );
  }
  for (const flag of [undefined, false, 1]) {
    expect(
      hasPricedCost(
        noSeparateWriteUsage({
          cost_rates: {
            input: 1.4,
            output: 4.4,
            cache_read: 0.26,
            cache_write: 0,
            cache_write_included: flag as unknown as boolean,
          },
        }),
      ),
    ).toBe(false);
  }
  expect(
    hasPricedCost(
      noSeparateWriteUsage({
        cost_rates: {
          input: 1.4,
          output: 4.4,
          cache_read: 0.26,
          cache_write: null,
          cache_write_included: true,
        },
      }),
    ),
  ).toBe(true);
  for (const writeRate of [0.1, -1, true, Number.NaN]) {
    expect(
      hasPricedCost(
        noSeparateWriteUsage({
          cost_rates: {
            input: 1.4,
            output: 4.4,
            cache_read: 0.26,
            cache_write: writeRate as number,
            cache_write_included: true,
          },
        }),
      ),
    ).toBe(false);
  }
});
