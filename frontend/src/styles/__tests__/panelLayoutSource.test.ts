import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");
const layout = source("../panels.css");
const chrome = source("../legacy-panels.css");
const components = source("../components.css");

test("panel spacing and compact header follow available panel width", () => {
  expect(layout).toMatch(/container-name:\s*panel;/);
  expect(layout).toMatch(/@container panel \(min-width: 640px\)/);
  expect(layout).toMatch(/@container panel \(min-width: 1024px\)/);
  expect(components).toMatch(/@container panel \(max-width: 639px\)/);
  expect(chrome).toMatch(
    /padding:\s*var\(--panel-header-block\) var\(--panel-inset\)/,
  );
  expect(chrome).toMatch(/margin-bottom:\s*0;/);
});

test("panel cards can shrink below their preferred column width", () => {
  expect(layout).toMatch(/\.auto-grid-cols > \*\s*\{\s*min-width:\s*0;/);
  expect(layout).toMatch(/minmax\(min\(100%, 20rem\), 1fr\)/);
});

test("compact panel controls remain touch sized and search-only headers have no top gap", () => {
  expect(layout).toMatch(
    /\.panel-header--search-only \.panel-header__search-row\s*\{\s*margin-top:\s*0;/,
  );
  expect(components).toMatch(
    /\.panel-header__mobile-more\s*\{[^}]*height:\s*2\.75rem;[^}]*width:\s*2\.75rem;/,
  );
});

test("settings navigation uses the available panel width", () => {
  expect(layout).toMatch(/@container panel \(max-width: 799px\)/);
  expect(layout).toMatch(/\.settings-sidebar\s*\{\s*display:\s*none;/);
  expect(source("../../components/panels/SettingsPanel.tsx")).toContain(
    "settings-toolbar panel-inset",
  );
});

test("page chrome and resource card actions use spacing instead of repeated dividers", () => {
  expect(chrome).not.toMatch(/border-bottom:\s*1px/);
  const cards = source("../card-base.css");
  const footer = cards.match(/\.scb__footer\s*\{([^}]+)\}/)?.[1];
  expect(footer).not.toContain("border-top");
  expect(footer).not.toContain("padding-top");
  expect(source("../../components/mcp/MCPServerCard.tsx")).toContain(
    'className="scb__footer flex',
  );
});

test("MCP form groups do not double their spacing with empty divider rows", () => {
  expect(source("../../components/mcp/MCPServerForm.tsx")).not.toContain(
    'className="es-divider"',
  );
});

test("search headers leave the search-to-content gap to the panel body", () => {
  expect(layout).toMatch(
    /\[data-panel\] \.panel-header\.panel-header--has-search\s*\{\s*padding-bottom:\s*0;/,
  );
});

test("file title and toolbar share the same search header spacing", () => {
  expect(layout).toMatch(
    /\[data-panel="files"\] \.panel-header\.panel-header--desktop-identity\s*\{\s*padding-bottom:\s*0;/,
  );
  expect(layout).toMatch(
    /\[data-panel\] \.file-library-toolbar\s*\{\s*padding-block:\s*var\(--panel-gap\) 0;/,
  );
});
