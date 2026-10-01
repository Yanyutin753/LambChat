import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const css = readFileSync("src/styles/components.css", "utf8");

test("custom panel artwork uses the same 48px square as regular panel headings", () => {
  expect(css).toMatch(
    /\.scene-illustration\.panel-avatar\s*\{[^}]*width: 3rem;[^}]*height: 3rem;/,
  );
});

test("mobile hides duplicate toolbar avatars while settings retains its tablet identity", () => {
  expect(css).toMatch(
    /@container panel \(max-width: 639px\)\s*\{[^}]*\.scene-illustration\.panel-avatar\s*\{[^}]*display: none;/,
  );
  expect(css).toMatch(
    /@container panel \(min-width: 640px\) and \(max-width: 799px\)/,
  );
  expect(
    readFileSync("src/components/panels/SettingsPanel.tsx", "utf8"),
  ).toContain('className="settings-compact-identity');
});

test("navigation avatar follows available content width rather than window width", () => {
  expect(css).toContain("@container panel-shell (min-width: 640px)");
  expect(
    readFileSync("src/components/layout/AppContent/AppShell.tsx", "utf8"),
  ).toContain("panel-shell");
});
