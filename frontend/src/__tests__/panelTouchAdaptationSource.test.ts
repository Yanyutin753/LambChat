import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * 移动端无 hover：面板/侧栏里 opacity-0 + group-hover:opacity-100 的
 * 交互元素必须带窄屏或无 hover 媒体查询兜底，否则触屏上永远不可见。
 */
function readComponent(...segments: string[]): string {
  return readFileSync(
    resolve(import.meta.dirname, "../components", ...segments),
    "utf8",
  );
}

const HOVER_REVEAL_FILES = [
  "panels/BookmarksPanel.tsx",
  "panels/MemoryPanel/index.tsx",
  "panels/AgentPanel/tabs/GlobalAgentTab.tsx",
  "sidebar/SessionItem.tsx",
  "sidebar/ProjectItem.tsx",
];

test.each(HOVER_REVEAL_FILES)(
  "%s keeps hover actions accessible on touch",
  (file) => {
    const source = readComponent(file);
    if (source.includes("sidebar-action-reveal")) {
      const css = readFileSync(
        resolve(import.meta.dirname, "../styles/components.css"),
        "utf8",
      );
      expect(css).not.toMatch(
        /@media \(hover: none\)\s*\{\s*html:not\(:has\(\[data-titlebar\]\)\) \.sidebar-action-reveal\s*\{\s*opacity: 1/,
      );
      expect(source).not.toContain("max-sm:opacity-100");
      expect(source).toContain("setIsTouched(true)");
      expect(source).toContain("isTouched || isMenuOpen");
      return;
    }
    const hoverReveals = source.match(/group-hover:opacity-100/g) ?? [];
    const touchFallbacks =
      source.match(
        /max-sm:opacity-100|\[@media\(hover:none\)\]:opacity-100/g,
      ) ?? [];
    // 该文件内的每一处 hover 显隐都要有移动端可见兜底
    expect(touchFallbacks.length).toBe(hoverReveals.length);
    expect(hoverReveals.length).toBeGreaterThan(0);
  },
);

test("role detail upload limits adapt to their container width", () => {
  const source = readComponent("panels/RoleDetailSidebar.tsx");
  expect(source).toMatch(/grid auto-grid-cols gap-x-4/);
  expect(source).not.toMatch(/sm:grid-cols-2/);
});

test("notification create action text follows hidden sm:inline convention", () => {
  const source = readComponent("panels/NotificationPanel.tsx");
  expect(source).toMatch(
    /<span className="hidden sm:inline">\{t\("notification\.create"\)\}<\/span>/,
  );
});
