import { expect, test } from "vitest";
import { getModelIconUrl, isMonochromeIcon } from "../modelIcon";

test.each([
  ["claude-sonnet-4", "openrouter", "anthropic"],
  ["openrouter/google/gemini-2.5-pro", "openai", "google"],
  ["deepseek-ai/DeepSeek-V3", "siliconflow", "deepseek"],
  ["glm-5.3", "openai", "zhipu"],
  ["gpt-4o", "azure", "openai"],
])("%s uses its model brand through %s", (model, provider, brand) => {
  expect(getModelIconUrl(model, provider)).toBe(
    getModelIconUrl("", undefined, brand),
  );
});

test("explicit icons accept picker aliases and override model inference", () => {
  expect(getModelIconUrl("gpt-4o", "openai", "lobe:claude")).toBe(
    getModelIconUrl("claude-sonnet-4"),
  );
  expect(getModelIconUrl("custom", " OpenAI ")).toBe(getModelIconUrl("gpt-4o"));
});

test("Kimi uses its own mark instead of the Moonshot company logo", () => {
  expect(getModelIconUrl("kimi-k2")).not.toBe(getModelIconUrl("moonshot-v1"));
});

test("unknown models retain provider fallback and missing brands return null", () => {
  expect(getModelIconUrl("custom", "openrouter")).toBe(
    getModelIconUrl("", undefined, "openrouter"),
  );
  expect(getModelIconUrl("custom")).toBeNull();
});

test("dark-mode treatment follows the selected brand", () => {
  expect(isMonochromeIcon("claude-sonnet-4", "openrouter")).toBe(false);
  expect(isMonochromeIcon("openrouter/google/gemini-2.5-pro")).toBe(false);
  expect(isMonochromeIcon("gpt-4o", "azure")).toBe(true);
});
