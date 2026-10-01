import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("content beside the activity rail has curved left corners on every page", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8")
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")");
  const shell = readFileSync(
    new URL("../../components/layout/AppContent/AppShell.tsx", import.meta.url),
    "utf8",
  );
  expect(shell).toContain('data-workspace-content=""');
  expect(css).toMatch(
    /\[data-workspace-content\]\s*\{[^}]*border-radius: var\(--radius-xl\) 0 0 var\(--radius-xl\);/,
  );
  expect(css).toMatch(
    /:has\(\[data-desktop-activity-rail\]\) > \[data-workspace-content\]/,
  );
});

test("dark workspace gives the sidebar its own theme-derived surface", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8")
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")");
  expect(css).toMatch(
    /html\.dark:has\(\[data-desktop-activity-rail\]\)\s*\{[^}]*--theme-bg-sidebar: color-mix\(in srgb, var\(--theme-bg\) 94%, var\(--theme-text\)\)/,
  );
});

test("activity rail surface takes priority over its utility background", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8")
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")");
  expect(css).toMatch(
    /\[data-desktop-sidebar-shell\] > \[data-desktop-activity-rail\]\s*\{[^}]*background: var\(--desktop-rail-bg\)/,
  );
});

test("dark desktop canvas and cards share a restrained theme palette", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8")
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")");
  expect(css).toContain(
    "--desktop-canvas-bg: color-mix(in srgb, var(--theme-bg) 97%, var(--theme-text))",
  );
  expect(css).toContain(
    "--theme-bg-card: color-mix(in srgb, var(--theme-bg) 88%, var(--theme-text))",
  );
  expect(css).toContain(
    "background: var(--desktop-canvas-bg, var(--theme-bg))",
  );
});

test("nested composer and fade surfaces inherit the desktop canvas color", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8")
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")");
  expect(css).toMatch(
    /:is\(\[data-workspace-content\], \.tool-console-panel, \.editor-sidebar\)\s*\{[^}]*--theme-bg: var\(--desktop-canvas-bg\)/,
  );
});

test("portalled previews share the workspace canvas and neutral chrome", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8")
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")");
  expect(css).toContain(
    ":is([data-workspace-content], .tool-console-panel, .editor-sidebar)",
  );
  expect(css).toContain(
    "--theme-bg-subtle: color-mix(in srgb, var(--theme-bg) 92%, var(--theme-text))",
  );
});

test("file paper previews use the shared surface instead of a fixed stone color", () => {
  const source = readFileSync(
    new URL(
      "../../components/fileLibrary/components/FileCardPreview.tsx",
      import.meta.url,
    ),
    "utf8",
  );
  expect(source).not.toContain("bg-stone-50 dark:bg-stone-900/60");
  expect(source).toContain(
    "relative h-full w-full overflow-hidden bg-theme-bg-subtle",
  );
});

test("preview tabs retain a quiet keyboard focus indicator", () => {
  const css = readFileSync(
    new URL("../../components/common/rightPanelTabs.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /button:focus-visible\s*\{[^}]*box-shadow: inset 0 -2px color-mix/,
  );
});

test("feedback summary uses shared themed surfaces", () => {
  const source = readFileSync(
    new URL("../../components/panels/FeedbackPanel.tsx", import.meta.url),
    "utf8",
  );
  expect(source).toContain(
    "panel-summary mb-4 p-4 rounded-2xl bg-theme-bg-card border border-theme-border",
  );
});
