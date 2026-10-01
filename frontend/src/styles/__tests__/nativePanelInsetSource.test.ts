import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("native overlay and fullscreen panels keep their headers below the titlebar", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
  const rule = css.match(
    /html:has\(\[data-titlebar\]\)\s+\[data-right-panel-root\]:not\(\[data-panel-presentation="docked"\]\)\s*\{([^}]+)\}/,
  )?.[1];
  expect(rule).toBeDefined();
  expect(rule).toContain("top: var(--titlebar-inset, 0px)");
  // EditorSidebar is itself fixed; ToolResultPanel has a fixed wrapper.
  expect(css).toMatch(
    /html:has\(\[data-titlebar\]\) \.editor-sidebar\[data-panel-presentation="overlay"\]\s*\{\s*--right-sidebar-height: calc\(100% - var\(--titlebar-inset, 0px\) - 1.5rem\)/,
  );
});
