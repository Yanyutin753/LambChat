import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("chats header exposes a dedicated select-mode button outside the more menu", () => {
  const source = readFileSync(
    resolve(__dirname, "../SessionListContent.tsx"),
    "utf8",
  );

  // ⋯ 菜单里的 menuItems 入口之外，头部操作行还要有常驻多选按钮
  expect(source).toMatch(/aria-label=\{t\("sidebar\.selectMode"\)\}/);
  expect(source).toMatch(/<ListChecks size=\{14\} \/>/);
  // 按钮复用 SidebarSectionHeader 导出的 hover 显隐样式，触屏常显
  expect(source).toMatch(
    /import \{[\s\S]*?sectionActionClass[\s\S]*?sectionRevealClass[\s\S]*?\} from "\.\/SidebarSectionHeader"/,
  );
});

test("SidebarSectionHeader exports the shared section action styles", () => {
  const source = readFileSync(
    resolve(__dirname, "../SidebarSectionHeader.tsx"),
    "utf8",
  );

  expect(source).toMatch(
    /export const sectionRevealClass =\s*"[^"]*sidebar-action-reveal[^"]*"/,
  );
  expect(source).toMatch(/export const sectionActionClass =\s*"/);
});
