import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SubagentBlocks.tsx", import.meta.url),
  "utf8",
);

test("subagent card chrome uses status-aware border treatment", () => {
  // Outer card ring
  expect(source).toMatch(/ring-1 ring-stone-300\/80 dark:ring-stone-600\/60/);
  // Status badge: running
  expect(source).toMatch(/ring-amber-300\/70 dark:ring-amber-700\/50/);
  // Status badge: complete
  expect(source).toMatch(/ring-emerald-300\/70 dark:ring-emerald-700\/50/);
  // Status badge: error
  expect(source).toMatch(/ring-red-300\/70 dark:ring-red-900\/45/);
  // Status badge: cancelled
  expect(source).toMatch(/bg-stone-200\/60 dark:bg-stone-700\/50/);
  // No primary-tinted card backgrounds
  expect(source).not.toMatch(
    /bg-\[color-mix\(in_srgb,var\(--theme-primary\)_7%,var\(--theme-bg-card\)\)\]/,
  );
  expect(source).not.toMatch(
    /ring-\[color-mix\(in_srgb,var\(--theme-primary\)_38%,transparent\)\]/,
  );
  // No amber/red-200 variants
  expect(source).not.toMatch(/ring-amber-200\/60/);
  expect(source).not.toMatch(/ring-red-200\/60/);
  expect(source).not.toMatch(/border-theme-border\/60/);
});

test("subagent status badge does not use theme-blue border chrome", () => {
  expect(source).toMatch(/shadow-sm ring-1/);
  expect(source).not.toMatch(/ring-theme-border\/70/);
  expect(source).not.toMatch(/subagent-border-pulse/);
});

test("subagent sidebar timestamp is rendered in the panel footer", () => {
  expect(source).toMatch(/function createSubagentPanelFooter/);
  expect(source).toMatch(/footer: createSubagentPanelFooter\(subtitle\)/);
  expect(source).not.toMatch(
    /subtitle,\s*\n\s*panelKey,\s*\n\s*children: <SubagentPanelContent/,
  );
});
