// token:usage 事件 → TokenUsagePart 的金额字段透传（实时与历史共用此处理器）
import { processMessageEvent } from "../eventProcessor.ts";

test("token:usage carries cost fields through to the message part", () => {
  const result = processMessageEvent(
    "token:usage",
    {
      input_tokens: 1000,
      output_tokens: 500,
      total_tokens: 1500,
      cache_read_tokens: 200,
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
});
