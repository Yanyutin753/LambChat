import { buildStreamingThinkingPreview } from "../thinkingPreview.ts";

test("returns empty string for empty content", () => {
  expect(buildStreamingThinkingPreview("")).toBe("");
  expect(buildStreamingThinkingPreview("   \n  ")).toBe("");
});

test("returns short content flattened as-is without truncation marker", () => {
  expect(buildStreamingThinkingPreview("分析需求")).toBe("分析需求");
});

test("collapses newlines and whitespace runs into single spaces", () => {
  expect(buildStreamingThinkingPreview("第一段\n\n\n   第二段")).toBe(
    "第一段 第二段",
  );
});

test("long content keeps only the last few characters without an ellipsis prefix", () => {
  const head = "前情提要".repeat(40); // 160 chars
  const tail = "最新进展".repeat(5); // 20 chars
  const preview = buildStreamingThinkingPreview(head + tail);
  expect(preview.startsWith("…")).toBe(false);
  expect(preview.endsWith(tail)).toBe(true);
  // at most 24 chars, no ellipsis prefix
  expect(preview.length).toBeLessThanOrEqual(24);
});

test("tail window survives content much longer than the preview cap", () => {
  const content = "句子。".repeat(500) + "结尾必须出现";
  const preview = buildStreamingThinkingPreview(content);
  expect(preview.endsWith("结尾必须出现")).toBe(true);
});

test("does not start with a dangling high surrogate from the tail slice", () => {
  const emoji = "🤔"; // surrogate pair
  const content = "a".repeat(300) + emoji + "思考中";
  const preview = buildStreamingThinkingPreview(content);
  // must not begin with a lone high surrogate (would render as replacement char)
  const first = preview.charCodeAt(0);
  expect(first < 0xd800 || first > 0xdbff).toBe(true);
});
