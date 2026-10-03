import { readFileSync } from "node:fs";

test("workspace toolbars and file menus share one responsive action size", () => {
  const css = readFileSync(
    new URL("../workspacePanel.css", import.meta.url),
    "utf8",
  );
  expect(css).toContain("--workspace-action-size: 32px");
  expect(css).toContain("--workspace-action-size: 44px");
  expect(css).toMatch(/width:\s*var\(--workspace-action-size\)/);
  expect(css).toMatch(/min-height:\s*var\(--workspace-action-size\)/);
  expect(css).toMatch(/\.workspace-cloud-status\s*\{[^}]*width:\s*var\(--workspace-action-size\)/);
});

test("workspace file tree uses regular sidebar text size", () => {
  const css = readFileSync(
    new URL("../workspacePanel.css", import.meta.url),
    "utf8",
  );
  // 文件名对齐其他侧边栏的正文字号（14px），不再是压缩的 13px
  expect(css).toMatch(/\.workspace-file-name\s*\{[^}]*font-size:\s*14px/);
  // 根节点「工作区」保持小标签层级但不小于 12px
  expect(css).toMatch(/\.workspace-root\s*\{[^}]*font-size:\s*12px/);
});

test("workspace tree directory rows use the same size as file names", () => {
  const source = readFileSync(
    new URL("../WorkspacePanel.tsx", import.meta.url),
    "utf8",
  );
  expect(source).toMatch(/<span className="truncate text-14 text-left">\{node\.name\}<\/span>/);
});
