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
