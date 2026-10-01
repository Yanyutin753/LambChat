import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("phone navigation and its action sheets use 44px controls without shrinking titles", () => {
  const css = read("../components.css");
  expect(css).toMatch(
    /@media \(max-width: 639px\)\s*\{\s*\.session-sidebar-drawer \.sidebar-action-row,\s*\.sidebar-nav-btn\s*\{[^}]*min-height:\s*2\.75rem;/,
  );
  expect(css).toMatch(
    /\.session-sidebar-drawer button,\s*\.sidebar-mobile-menu button\s*\{[^}]*min-width:\s*2\.75rem;[^}]*min-height:\s*2\.75rem;/,
  );
  expect(css).toMatch(/\.sidebar-action-controls\s*\{\s*gap:\s*0;/);
  expect(read("../../components/panels/SessionSidebar.tsx")).toContain(
    "session-sidebar-drawer",
  );
  const sidebar = read(
    "../../components/panels/SidebarParts/SessionListContent.tsx",
  );
  expect(sidebar).toContain("gap-0 sm:gap-px");
  expect(sidebar).toContain("space-y-0 sm:space-y-1");
  expect(sidebar).toContain("h-9 max-sm:h-11 items-center");
  expect(css).toMatch(
    /\.session-sidebar-drawer input\s*\{[^}]*min-height:\s*2\.75rem;[^}]*font-size:\s*1rem;/,
  );
  expect(read("../chat.css")).toContain(
    ".feature-menu-dropdown .feature-menu-item:focus-visible,",
  );
});
