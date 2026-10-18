import { readFileSync, readdirSync } from "node:fs";
import postcss from "postcss";
import { expect, test } from "vitest";

const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");

function ungatedReveals(source: string) {
  const violations: string[] = [];
  postcss.parse(source).walkRules((rule) => {
    if (!rule.selector.includes(".sidebar-action-reveal")) return;
    let reveals = false;
    rule.walkDecls((decl) => {
      if (
        (decl.prop === "opacity" && Number(decl.value) > 0) ||
        (decl.prop === "pointer-events" && decl.value === "auto")
      ) {
        reveals = true;
      }
    });
    if (!reveals) return;
    let desktopOnly = false;
    for (let parent = rule.parent; parent; parent = parent.parent) {
      if (
        parent.type === "atrule" &&
        parent.name === "media" &&
        parent.params.replace(/\s/g, "") === "(hover:hover)and(pointer:fine)"
      ) {
        desktopOnly = true;
      }
    }
    for (const selector of rule.selectors) {
      if (
        !/\[data-revealed=["']true["']\]|:focus-visible/.test(selector) &&
        !desktopOnly
      ) {
        violations.push(selector);
      }
    }
  });
  return violations;
}

test("no stylesheet makes sidebar actions visible without touch, keyboard focus or a desktop pointer", () => {
  for (const file of readdirSync(
    new URL("../../../styles/", import.meta.url),
  )) {
    if (!file.endsWith(".css")) continue;
    expect(ungatedReveals(read(`../../../styles/${file}`)), file).toEqual([]);
  }
});

test.each([
  "@media (hover: none), (pointer: coarse)",
  "@media (pointer: coarse)",
  "@media (max-width: 639px)",
  "@media (hover: hover)",
  "",
])("the CSS guard detects an always-visible regression under %s", (media) => {
  const regression =
    ".sidebar-action-reveal { opacity: 1; pointer-events: auto; }";
  expect(
    ungatedReveals(media ? `${media} { ${regression} }` : regression),
  ).toEqual([".sidebar-action-reveal"]);
});

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
  expect(css).toMatch(/\.sidebar-action-reveal:where\([^}]+opacity: 0/s);
  expect(css).toMatch(
    /\.sidebar-action-reveal:where\([^}]+pointer-events: none/s,
  );
  expect(css).toContain('[data-revealed="true"]');
  expect(css).not.toMatch(
    /@media \(hover: none\), \(pointer: coarse\)\s*\{\s*\.sidebar-action-reveal/,
  );
  expect(css).toMatch(
    /@media \(hover: hover\) and \(pointer: fine\)\s*\{\s*\.sidebar-action-row:hover/,
  );
  expect(css).toContain(":has(:focus-visible)");
  expect(css).not.toContain(".sidebar-action-row:focus-within");
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
