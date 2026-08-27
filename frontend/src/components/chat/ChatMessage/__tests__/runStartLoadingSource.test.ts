import { readFileSync } from "node:fs";

test("streaming run with no parts keeps the working row and shows a loading icon under the divider", () => {
  const source = readFileSync(new URL("../index.tsx", import.meta.url), "utf8");

  // 工作行（含分割线）保留，空态不退化为纯 icon
  expect(source).toMatch(/steps=\{0\}/);
  // 展开区内渲染加载 icon，而不是 null
  expect(source).toMatch(/renderExpanded=\{\(\) => \(\s*<Loader2/);
  expect(source).toMatch(/<Loader2[^>]*animate-spin/);
});
