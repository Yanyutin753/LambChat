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
  expect(css).not.toContain("--right-panel-header-height: 3rem");
  const tabs = readFileSync(
    new URL("../rightPanelTabs.css", import.meta.url),
    "utf8",
  );
  expect(tabs).toMatch(/\.right-panel-tabs\s*\{[^}]*flex-wrap: nowrap;/);
  expect(tabs).toMatch(/\.right-panel-tabs\s*\{[^}]*overflow: clip;/);
  expect(tabs).toMatch(/\.right-panel-tab\s*\{[^}]*min-width: 0;/);
  expect(tabs).not.toMatch(/overflow-y: (auto|scroll)/);
  const component = readFileSync(
    new URL("../RightPanelTabs.tsx", import.meta.url),
    "utf8",
  );
  expect(component).toContain("if (window.innerWidth >= 640) return;");
  expect(tabs).toMatch(
    /\.right-panel-tab\[data-selected="true"\]\s*\{[^}]*min-width: 4\.75rem;/,
  );
  expect(tabs).toMatch(
    /@container right-panel-tab \(max-width: 6rem\)\s*\{\s*\.right-panel-tab:not\(\[data-selected="true"\]\) > \.right-panel-tab-close\s*\{\s*display: none;/,
  );
  expect(workspace).not.toContain("[&_.tool-console-header]");
});

test("phone tabs scroll horizontally while the strip blocks vertical scrolling", () => {
  const tabs = readFileSync(
    new URL("../rightPanelTabs.css", import.meta.url),
    "utf8",
  );
  const phone = tabs.slice(tabs.lastIndexOf("@media (max-width: 639px)"));
  expect(phone).toMatch(
    /\.right-panel-tab-scroll\s*\{[^}]*overflow-x: auto;[^}]*overflow-y: hidden;/,
  );
  expect(phone).toMatch(/\.right-panel-tab\s*\{[^}]*flex: 1 0 10rem;/);
  expect(phone).toMatch(
    /\.right-panel-tab-scroll > \.right-panel-tabs\s*\{[^}]*flex: 1 0 auto;/,
  );
});

test("compact document toolbars keep touch actions and close reachable without squeezing the title", () => {
  const css = readFileSync(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(/@container document-toolbar \(max-width: 479px\)/);
  expect(css).toMatch(
    /\.document-preview-toolbar button\[type\]\s*\{[^}]*min-width: 2.25rem;[^}]*min-height: 2.25rem;/,
  );
  expect(css).toMatch(/\.document-preview-language\s*\{[^}]*display: none;/);
  expect(css).toMatch(
    /\.document-preview-more-actions\s*\{[^}]*display: block;/,
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

test("phone tab controls use compact icon targets and tighter label gaps", () => {
  const tabs = readFileSync(
    new URL("../rightPanelTabs.css", import.meta.url),
    "utf8",
  );
  const touch = tabs.slice(
    tabs.indexOf("@media (pointer: coarse), (max-width: 639px)"),
  );
  expect(touch).not.toMatch(
    /\.right-panel-tab > \.right-panel-tab-close\s*\{[^}]*width: 2\.75rem;/,
  );
  expect(touch).toMatch(
    /\.right-panel-tab \[role="tab"\]\s*\{[^}]*gap: 0\.375rem;/,
  );
});
