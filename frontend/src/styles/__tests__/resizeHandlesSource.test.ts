import { readFileSync } from "node:fs";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("all workspace separators share one transparent rail and interaction treatment", () => {
  for (const path of [
    "../../components/layout/DesktopSidebarShell/DesktopSidebarShell.tsx",
    "../../components/common/EditorSidebar.tsx",
    "../../components/chat/ChatMessage/items/ToolResultPanel.tsx",
  ]) {
    expect(read(path)).toContain("workspace-resize-handle");
  }
  const css = read("../components.css");
  expect(css).toMatch(
    /\.workspace-resize-handle\s*\{[^}]*background:\s*transparent;/,
  );
  expect(css).toMatch(
    /\.workspace-resize-handle > div\s*\{[^}]*width:\s*1px;[^}]*box-shadow:\s*none;/,
  );
  expect(css).toContain("background: var(--theme-border-hover);");
  expect(css).toContain(".workspace-resize-handle:hover > div");
  expect(css).toContain(".workspace-resize-handle:focus-visible > div");
});
