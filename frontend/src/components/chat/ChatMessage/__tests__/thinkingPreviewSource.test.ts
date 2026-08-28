import { readFileSync } from "node:fs";

test("ThinkingBlock appends the live tail preview to the streaming label", () => {
  const source = readFileSync(
    new URL("../ThinkingBlock.tsx", import.meta.url),
    "utf8",
  );

  // 流式分支用尾部预览而非空串，保证标签随 delta 动态更新
  expect(source).toMatch(/if \(isStreaming\) return buildStreamingThinkingPreview\(content\);/);
  // 标签拼上「思考中」前缀
  expect(source).toMatch(/`\$\{t\("chat\.message\.thinking"\)\} \$\{preview\}`/);
});
