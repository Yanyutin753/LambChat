import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("editor, tool and document panels share fixed header geometry without workspace overrides", () => {
  const css = readFileSync(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );
  const workspace = readFileSync(
    new URL("../../workspacePanel/SessionWorkspaceButton.tsx", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\[data-right-panel-root\]\s+:is\(\s*\.editor-sidebar-header,\s*\.tool-console-header,\s*\.document-preview-toolbar\s*\)\s*\{[^}]*height: var\(--right-panel-header-height\);[^}]*min-height: var\(--right-panel-header-height\);[^}]*padding: 0 /,
  );
  expect(css).toContain("--right-panel-header-height: 2.75rem");
  expect(css).toContain("--right-panel-header-height: 3rem");
  const tabs = readFileSync(
    new URL("../rightPanelTabs.css", import.meta.url),
    "utf8",
  );
  expect(tabs).toMatch(/\.right-panel-tabs\s*\{[^}]*flex-wrap: wrap;/);
  expect(tabs).not.toContain("overflow-x: auto");
  expect(workspace).not.toContain("[&_.tool-console-header]");
});

test("compact document toolbars keep touch actions and close reachable without squeezing the title", () => {
  const css = readFileSync(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(/@media \(max-width: 1199px\), \(pointer: coarse\)/);
  expect(css).toMatch(
    /\.document-preview-toolbar button\s*\{[^}]*min-width: 2.75rem;[^}]*min-height: 2.75rem;/,
  );
  expect(css).toMatch(
    /\.document-preview-toolbar-actions\s*\{[^}]*position: static;[^}]*flex-basis: 100%;/,
  );
  expect(css).toMatch(
    /\.document-preview-toolbar-actions > button:last-child\s*\{[^}]*position: absolute;/,
  );
});

test("tablet overlay panels use the available width instead of desktop lane width", () => {
  const css = readFileSync(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\.editor-sidebar\[data-panel-presentation="overlay"\],[\s\S]*?width: min\(40rem, calc\(100vw - 1.5rem\)\) !important;/,
  );
});
