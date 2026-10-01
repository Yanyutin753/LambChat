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

test("activity rail surface takes priority over its utility background", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8")
    .replace(/\s+/g, " ")
    .replace(/\(\s+/g, "(")
    .replace(/\s+\)/g, ")");
  expect(css).toMatch(
    /\[data-desktop-sidebar-shell\] > \[data-desktop-activity-rail\]\s*\{[^}]*background: var\(--desktop-rail-bg\)/,
  );
});

test("desktop rail keeps its original distinct tint without recursive theme aliases", () => {
  const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
  expect(css).not.toMatch(/--theme-bg(?:-card|-subtle|-elevated|-sidebar)?:/);
  expect(css).not.toContain("--desktop-canvas-bg:");
  expect(css.replace(/\s+/g, " ")).toMatch(/--desktop-rail-bg: color-mix\( in srgb, var\(--theme-bg-sidebar\) 94%, var\(--theme-text\) \)/);
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
