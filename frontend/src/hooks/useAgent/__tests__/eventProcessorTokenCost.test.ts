// token:usage 事件 → TokenUsagePart 的金额字段透传（实时与历史共用此处理器）
import { processMessageEvent } from "../eventProcessor.ts";
import {
  formatUsageTokenCount,
  formatTokenUsageCost,
  hasPricedCost,
} from "../../../components/chat/ChatMessage/tokenCostDisplay";

test("read denominator certificate survives live and historical event reconstruction without pricing missing writes", () => {
  const result = processMessageEvent(
    "token:usage",
    {
      input_tokens: 100,
      output_tokens: 5,
      cache_read_tokens: 80,
      input_includes_cache: true,
      unknown_usage_fields: ["cache_creation_tokens"],
    },
    [],
    "",
    [],
    0,
    [],
    false,
    "certified-rate",
  );
  expect(result.tokenUsage?.input_includes_cache).toBe(true);
  expect(result.tokenUsage?.cache_creation_tokens).toBeUndefined();
  expect(result.tokenUsage?.usage_incomplete).toBe(true);
  expect(result.tokenUsage?.cost_usd).toBeUndefined();
});

test("token:usage carries cost fields through to the message part", () => {
  const result = processMessageEvent(
    "token:usage",
    {
      input_tokens: 1000,
      output_tokens: 500,
      total_tokens: 1500,
      cache_read_tokens: 200,
      cache_creation_tokens: 0,
      usage_incomplete: false,
      model_id: "model-1",
      model: "openai/gpt-4o",
      cost_usd: 0.0246,
      cost_breakdown: {
        input: 0.002,
        output: 0.005,
        cache_read: 0.0002,
        cache_write: 0,
        total: 0.0246,
      },
      cost_rates: {
        input: 2.5,
        output: 10,
        cache_read: 1.25,
        cache_write: null,
      },
    },
    [],
    "",
    [],
    0,
    [],
    false,
    "message-1",
  );

  expect(result.tokenUsage).toEqual({
    type: "token_usage",
    input_tokens: 1000,
    output_tokens: 500,
    total_tokens: 1500,
    cache_creation_tokens: 0,
    cache_read_tokens: 200,
    usage_incomplete: false,
    model_id: "model-1",
    model: "openai/gpt-4o",
    cost_usd: 0.0246,
    cost_breakdown: {
      input: 0.002,
      output: 0.005,
      cache_read: 0.0002,
      cache_write: 0,
      total: 0.0246,
    },
    cost_rates: { input: 2.5, output: 10, cache_read: 1.25, cache_write: null },
  });
});

test("token:usage without pricing keeps cost fields undefined", () => {
  const result = processMessageEvent(
    "token:usage",
    {
      input_tokens: 10,
      output_tokens: 5,
      total_tokens: 15,
      model: "mystery",
    },
    [],
    "",
    [],
    0,
    [],
    false,
    "message-1",
  );

  expect(result.tokenUsage?.cost_usd).toBeUndefined();
  expect(result.tokenUsage?.cost_breakdown).toBeUndefined();
  expect(result.tokenUsage?.cost_rates).toBeUndefined();
  expect(result.tokenUsage?.cache_read_tokens).toBeUndefined();
  expect(result.tokenUsage?.cache_creation_tokens).toBeUndefined();
  expect(result.tokenUsage?.usage_incomplete).toBe(true);
});

test("explicit cache zero remains known zero", () => {
  const result = processMessageEvent(
    "token:usage",
    {
      input_tokens: 10,
      output_tokens: 5,
      total_tokens: 15,
      cache_read_tokens: 0,
      cache_creation_tokens: 0,
      usage_incomplete: false,
    },
    [],
    "",
    [],
    0,
    [],
    false,
    "zero-usage",
  );
  expect(result.tokenUsage?.cache_read_tokens).toBe(0);
  expect(result.tokenUsage?.cache_creation_tokens).toBe(0);
  expect(result.tokenUsage?.usage_incomplete).toBe(false);
});

test("live and historical events preserve partial zero and separate estimates", () => {
  const result = processMessageEvent(
    "token:usage",
    {
      input_tokens: 100,
      output_tokens: 0,
      partial_cost_usd: 0,
      partial_cost_breakdown: { output: 0 },
      estimated_cost_usd: 0.25,
    },
    [],
    "",
    [],
    0,
    [],
    false,
    "partial-message",
  );
  expect(result.tokenUsage?.partial_cost_usd).toBe(0);
  expect(result.tokenUsage?.partial_cost_breakdown).toEqual({ output: 0 });
  expect(result.tokenUsage?.estimated_cost_usd).toBe(0.25);
  expect(result.tokenUsage?.cost_usd).toBeUndefined();
});

test.each([undefined, 1])(
  "legacy complete counters remain reportable without turning completeness %s into a certificate",
  (flag) => {
    const result = processMessageEvent(
      "token:usage",
      {
        input_tokens: 1000,
        output_tokens: 500,
        total_tokens: 1500,
        cache_read_tokens: 200,
        cache_creation_tokens: 0,
        usage_incomplete: flag as unknown as boolean,
        input_includes_cache: true,
        cost_usd: 0.4,
      },
      [],
      "",
      [],
      0,
      [],
      false,
      "legacy-report",
    );
    expect(result.tokenUsage?.usage_incomplete).toBeUndefined();
    expect(formatUsageTokenCount(result.tokenUsage!, "output_tokens")).toBe(
      "500",
    );
    expect(hasPricedCost(result.tokenUsage)).toBe(false);
    expect(formatTokenUsageCost(result.tokenUsage, { language: "en" })).toBe(
      "≈$0.4",
    );
  },
);

test("an explicit incomplete event with no field list still hides its counters", () => {
  const result = processMessageEvent(
    "token:usage",
    {
      input_tokens: 1000,
      output_tokens: 500,
      total_tokens: 1500,
      cache_read_tokens: 200,
      cache_creation_tokens: 0,
      usage_incomplete: true,
    },
    [],
    "",
    [],
    0,
    [],
    false,
    "explicit-incomplete",
  );
  expect(result.tokenUsage?.usage_incomplete).toBe(true);
  expect(formatUsageTokenCount(result.tokenUsage!, "output_tokens")).toBe("—");
});

test("events retain financial completeness independently of missing cache write tokens", () => {
  const result = processMessageEvent(
    "token:usage",
    {
      input_tokens: 12822,
      output_tokens: 86,
      total_tokens: 12908,
      cache_read_tokens: 10880,
      usage_incomplete: true,
      unknown_usage_fields: ["cache_creation_tokens"],
      input_includes_cache: true,
      cost_complete: true,
      cost_usd: 0.005926,
      cost_rates: {
        input: 1.4,
        output: 4.4,
        cache_read: 0.26,
        cache_write: 0,
        cache_write_included: true,
      },
    },
    [],
    "",
    [],
    0,
    [],
    false,
    "no-separate-write",
  );
  expect(result.tokenUsage?.cost_complete).toBe(true);
  expect(result.tokenUsage?.usage_incomplete).toBe(true);
  expect(result.tokenUsage?.cache_creation_tokens).toBeUndefined();
  expect(hasPricedCost(result.tokenUsage)).toBe(true);
  expect(formatTokenUsageCost(result.tokenUsage, { language: "en" })).toBe(
    "$0.005926",
  );
});

test.each([true, false])(
  "settled costs survive live and historical conversion (complete=%s)",
  (complete) => {
    const actualModels = [
      { model: "fallback", model_id: "b", provider: "openai" },
    ];
    for (const streaming of [true, false]) {
      const result = processMessageEvent(
        "token:usage",
        {
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          unknown_usage_fields: ["input_tokens"],
          model: "fallback",
          model_id: "b",
          cost_source: "provider_settlement",
          cost_units: 123_000_000,
          cost_complete: complete,
          actual_models: actualModels,
          ...(complete ? { cost_usd: 0.123 } : { partial_cost_usd: 0.123 }),
        },
        [],
        "",
        [],
        0,
        [],
        streaming,
        "receipt",
      );
      expect(result.tokenUsage).toMatchObject({
        cost_source: "provider_settlement",
        cost_units: 123_000_000,
        cost_complete: complete,
        actual_models: actualModels,
        model: "fallback",
      });
      expect(result.tokenUsage?.input_includes_cache).toBeUndefined();
      expect(hasPricedCost(result.tokenUsage)).toBe(complete);
      expect(
        formatTokenUsageCost(result.tokenUsage, { language: "en" }),
      ).toContain("0.123");
      expect(result.tokenUsage?.cost_rates).toBeUndefined();
    }
  },
);
