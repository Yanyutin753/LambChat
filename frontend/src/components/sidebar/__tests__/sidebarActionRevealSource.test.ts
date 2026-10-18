import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

test("sidebar actions share slots and reveal only within their own row", () => {
  const project = read("../ProjectItem.tsx");
  const session = read("../SessionItem.tsx");
  const header = read("../../panels/SidebarParts/SidebarSectionHeader.tsx");
  const css = read("../../../styles/components.css");
  for (const source of [project, session, header]) {
    expect(source).toContain("sidebar-action-reveal");
    expect(source).toContain("sidebar-action-row");
  }
  expect(session).not.toContain("max-sm:opacity-100");
  expect(session).toContain("h-8 w-6");
  expect(header).toContain("h-8 w-6");
  expect(css).toContain(".sidebar-action-row:hover > .sidebar-action-reveal");
  expect(css).not.toContain(
    "html:not(:has([data-titlebar])) .sidebar-action-reveal",
  );
});

test("sidebar feedback stays local and hidden actions cannot intercept the pointer", () => {
  const css = read("../../../styles/components.css");
  expect(css).toMatch(
    /\.sidebar-action-reveal:where\([^}]+pointer-events: none/s,
  );
  expect(css).toContain('[data-revealed="true"]');
  expect(css).toContain("@media (hover: none), (pointer: coarse)");
  expect(read("../SessionItem.tsx")).toContain("group-hover/session:");
  expect(read("../ProjectItem.tsx")).not.toContain(
    '"bg-stone-100 dark:bg-stone-700/50"',
  );
  expect(read("../../panels/SidebarParts/SessionListContent.tsx")).toContain(
    "group-focus-within/nav:opacity-100",
  );
  expect(read("../../../styles/desktop.css")).toContain(
    'button:not(:disabled):not([aria-pressed="true"]):hover',
  );
});
