import { expect, test } from "vitest";
import type { TokenUsagePart } from "../../../types/message";
import { formatUsageTokenCount } from "../tokenCostDisplay";

function usage(overrides: Partial<TokenUsagePart> = {}): TokenUsagePart {
  return {
    type: "token_usage",
    input_tokens: 4517,
    output_tokens: 3302,
    total_tokens: 7819,
    usage_incomplete: false,
    ...overrides,
  };
}

test("unreported input cannot look like a measured zero", () => {
  expect(
    formatUsageTokenCount(
      usage({
        input_tokens: 0,
        usage_incomplete: true,
        unknown_usage_fields: ["input_tokens"],
      }),
      "input_tokens",
    ),
  ).toBe("—");
});

test("a known subtotal cannot look like the entire interrupted call", () => {
  expect(
    formatUsageTokenCount(
      usage({ usage_incomplete: true, unknown_usage_fields: ["input_tokens"] }),
      "input_tokens",
    ),
  ).toBe("—");
});

test("explicit measured zero remains zero and missing cache-write does not hide known input", () => {
  expect(
    formatUsageTokenCount(usage({ input_tokens: 0 }), "input_tokens"),
  ).toBe("0");
  expect(
    formatUsageTokenCount(
      usage({
        usage_incomplete: true,
        unknown_usage_fields: ["cache_creation_tokens"],
      }),
      "input_tokens",
    ),
  ).toBe((4517).toLocaleString());
});

test("legacy incomplete counts and absent cache counts remain unknown", () => {
  expect(
    formatUsageTokenCount(usage({ usage_incomplete: true }), "input_tokens"),
  ).toBe("—");
  expect(formatUsageTokenCount(usage(), "cache_read_tokens")).toBe("—");
});
