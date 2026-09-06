import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * 移动端无 hover：面板/侧栏里 opacity-0 + group-hover:opacity-100 的
 * 交互元素必须带 max-sm:opacity-100 兜底，否则触屏上永远不可见。
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
  "%s keeps every hover-reveal visible on touch",
  (file) => {
    const source = readComponent(file);
    const hoverReveals = source.match(/group-hover:opacity-100/g) ?? [];
    const touchFallbacks = source.match(/max-sm:opacity-100/g) ?? [];
    // 该文件内的每一处 hover 显隐都要有移动端可见兜底
    expect(touchFallbacks.length).toBe(hoverReveals.length);
    expect(hoverReveals.length).toBeGreaterThan(0);
  },
);

test("role detail upload limits stack on narrow screens", () => {
  const source = readComponent("panels/RoleDetailSidebar.tsx");
  expect(source).toMatch(/grid grid-cols-1 sm:grid-cols-2 gap-x-4/);
});

test("notification create action text follows hidden sm:inline convention", () => {
  const source = readComponent("panels/NotificationPanel.tsx");
  expect(source).toMatch(
    /<span className="hidden sm:inline">\{t\("notification\.create"\)\}<\/span>/,
  );
});
