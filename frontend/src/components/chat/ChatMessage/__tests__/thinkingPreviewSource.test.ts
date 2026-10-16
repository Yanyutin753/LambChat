import { readFileSync } from "node:fs";

test("ThinkingBlock appends the live tail preview to the streaming label", () => {
  const source = readFileSync(
    new URL("../ThinkingBlock.tsx", import.meta.url),
    "utf8",
  );

  // 流式分支用尾部预览而非空串，保证标签随 delta 动态更新
  expect(source).toMatch(
    /if \(isStreaming\) return buildStreamingThinkingPreview\(displayContent\);/,
  );
  // Keep the live preview separate from the stable status title.
  expect(source).toContain(
    'const label = isStreaming ? t("chat.message.thinking") : settledLabel;',
  );
  expect(source).toContain("description={preview}");
});
