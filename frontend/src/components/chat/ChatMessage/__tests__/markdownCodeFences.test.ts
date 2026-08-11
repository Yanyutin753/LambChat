import { normalizeMarkdownCodeFences } from "../markdownCodeFences.ts";

test("adds a line break before an opening fence attached to prose", () => {
  expect(
    normalizeMarkdownCodeFences('before```json\n{"ok":true}\n```\nafter'),
  ).toBe('before\n```json\n{"ok":true}\n```\nafter');
});

test("keeps inline code spans untouched", () => {
  expect(normalizeMarkdownCodeFences("Use `const value = 1` inline.")).toBe(
    "Use `const value = 1` inline.",
  );
});

test("does not add extra line breaks to already valid fenced code blocks", () => {
  const markdown = "before\n```ts\nconst value = 1;\n```\nafter";

  expect(normalizeMarkdownCodeFences(markdown)).toBe(markdown);
});

test("does not treat a language-tagged marker as a closing fence", () => {
  const markdown = [
    "```systemverilog",
    "logic [45:0] pmu_rst_ctrl_ack;",
    "logic## 1. 如何调用 SRAM model",
    "",
    "```systemverilog",
    "task preloadData",
    "```",
    "",
    "### 形式 A：任务不带参数",
    "",
    "```systemverilog",
    "task preloadData;",
    "endtask",
    "```",
  ].join("\r\n");

  expect(normalizeMarkdownCodeFences(markdown)).toBe(markdown);
});
