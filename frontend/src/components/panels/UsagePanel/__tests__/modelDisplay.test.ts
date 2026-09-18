import {
  buildModelLabelMap,
  modelDisplayName,
  withModelDisplayNames,
} from "../modelDisplay";
import type { UsageRankingItem } from "../../../../types/usage";

function rankingItem(
  overrides: Partial<UsageRankingItem> = {},
): UsageRankingItem {
  return {
    id: "glm-4.7",
    name: "glm-4.7",
    requests: 3,
    tokens: 1200,
    duration: 42,
    input_tokens: 900,
    cache_creation_tokens: 0,
    cache_read_tokens: 0,
    cache_read_share: 0,
    zero_cache_requests: 0,
    ...overrides,
  };
}

test("buildModelLabelMap maps model value to label", () => {
  const map = buildModelLabelMap([
    { value: "glm-4.7", label: "GLM 4.7" },
    { value: "deepseek-chat", label: "DeepSeek V4" },
  ]);
  expect(map.get("glm-4.7")).toBe("GLM 4.7");
  expect(map.get("deepseek-chat")).toBe("DeepSeek V4");
});

test("buildModelLabelMap skips entries without value or label", () => {
  const map = buildModelLabelMap([
    { value: "", label: "幽灵模型" },
    { value: "no-label-model" },
    { value: "blank-label-model", label: "  " },
  ]);
  expect(map.size).toBe(0);
});

test("buildModelLabelMap tolerates null or undefined model list", () => {
  expect(buildModelLabelMap(null).size).toBe(0);
  expect(buildModelLabelMap(undefined).size).toBe(0);
});

test("modelDisplayName returns label when model is known", () => {
  const labels = buildModelLabelMap([{ value: "glm-4.7", label: "GLM 4.7" }]);
  expect(modelDisplayName(labels, "glm-4.7")).toBe("GLM 4.7");
});

test("modelDisplayName falls back to raw value when model is unknown", () => {
  const labels = buildModelLabelMap([{ value: "glm-4.7", label: "GLM 4.7" }]);
  expect(modelDisplayName(labels, "gpt-9")).toBe("gpt-9");
});

test("modelDisplayName returns empty string for empty model", () => {
  const labels = buildModelLabelMap([{ value: "glm-4.7", label: "GLM 4.7" }]);
  expect(modelDisplayName(labels, "")).toBe("");
  expect(modelDisplayName(labels, null)).toBe("");
});

test("withModelDisplayNames swaps ranking names to labels without mutating input", () => {
  const labels = buildModelLabelMap([{ value: "glm-4.7", label: "GLM 4.7" }]);
  const items = [
    rankingItem({ id: "glm-4.7", name: "glm-4.7" }),
    rankingItem({ id: "legacy-model", name: "legacy-model" }),
  ];
  const result = withModelDisplayNames(items, labels);
  expect(result[0].name).toBe("GLM 4.7");
  expect(result[1].name).toBe("legacy-model");
  expect(items[0].name).toBe("glm-4.7");
});
