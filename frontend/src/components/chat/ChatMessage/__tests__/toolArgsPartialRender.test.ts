import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * 工具参数流式（tool:args:chunk）依赖 ToolCallItem 既有的 args.partial
 * 展示分支渲染生成中的参数。该契约被钉死在这里：渲染组件不为流式参数
 * 引入新 UI，partial 形态走 JSON.parse 回退原样文本的既有路径。
 */
test("ToolCallItem keeps the args.partial rendering branch for streamed args", () => {
  const source = readFileSync(
    path.join(__dirname, "../../ChatMessage/ToolCallItem.tsx"),
    "utf-8",
  );

  expect(source).toMatch(/args\.partial !== undefined/);
  expect(source).toMatch(/JSON\.parse\(args\.partial as string\)/);
  expect(source).toMatch(/return \{ partial: args\.partial \};/);
});
