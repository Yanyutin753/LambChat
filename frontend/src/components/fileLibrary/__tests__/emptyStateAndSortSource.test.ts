import { existsSync, readFileSync } from "node:fs";
function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return existsSync(url) ? readFileSync(url, "utf8") : "";
}

const emptySource = readSource("../components/EmptyState.tsx");
const toolbarSource = readSource("../components/Toolbar.tsx");

test("file library empty state offers a path into chat", () => {
  // 无文件(且无筛选)时给出"去开启对话"引导,而不是只留一句空态文案
  expect(emptySource).toMatch(/useNavigate/);
  expect(emptySource).toMatch(/navigate\("\/chat"\)/);
  expect(emptySource).toMatch(/fileLibrary\.emptyAction/);
});

test("sort trigger shows a single sort glyph, direction stays in the menu", () => {
  // 触发按钮不再渲染方向箭头 SortIcon(方向已由选项文案承载),
  // 窄屏保留一个排序图标,避免"两个下拉箭头并排"的歧义
  expect(toolbarSource).not.toMatch(/<SortIcon\s+order=\{sortOrder\}/);
  expect(toolbarSource).toMatch(/ArrowUpDown/);
});
