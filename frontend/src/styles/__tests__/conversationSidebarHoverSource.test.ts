import { readFileSync } from "node:fs";
import { join } from "node:path";

const read = (path: string) =>
  readFileSync(join(import.meta.dirname, "../../", path), "utf8");

test("conversation sidebar controls use foreground feedback without hover fills", () => {
  for (const path of [
    "components/sidebar/SessionItem.tsx",
    "components/sidebar/ProjectItem.tsx",
    "components/sidebar/ProjectWorkspaceField.tsx",
    "components/sidebar/SessionMenu.tsx",
    "components/panels/SidebarParts/SidebarSectionHeader.tsx",
    "components/panels/SidebarParts/SessionListContent.tsx",
    "components/panels/SidebarParts/SidebarUserRow.tsx",
    "components/panels/SidebarParts/MobileMoreMenuSheet.tsx",
  ]) {
    expect(read(path), path).not.toMatch(/(?:dark:)?hover:bg-/);
  }
  for (const path of ["styles/base.css", "styles/desktop.css"]) {
    const rules =
      read(path).match(/[^{}]*\.sidebar-nav-btn:hover\s*\{[^}]*\}/g) ?? [];
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) expect(rule).not.toMatch(/background/);
  }
  expect(read("components/sidebar/SessionItem.tsx")).toContain(
    '"bg-theme-bg-subtle dark:bg-stone-700/50"',
  );
});
