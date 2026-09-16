import { readFileSync } from "node:fs";
import { join } from "node:path";

const panelSource = readFileSync(
  join(import.meta.dirname, "../SettingsPanel.tsx"),
  "utf8",
);

const utilitiesSource = readFileSync(
  join(import.meta.dirname, "../../../styles/utilities.css"),
  "utf8",
);

test("desktop and mobile share the same grouped category navigation", () => {
  expect(panelSource.match(/<SettingsCategoryNav/g)).toHaveLength(2);
  expect(panelSource.match(/categories=\{visibleCategories\}/g)).toHaveLength(
    2,
  );
});

test("json textarea stays scrollable instead of filling the mobile viewport", () => {
  expect(panelSource).toMatch(/rows=\{20\}[\s\S]{0,400}?max-h-\[/);
});

test("scrollbar-none utility actually hides scrollbars", () => {
  expect(utilitiesSource).toMatch(
    /\.scrollbar-none \{[\s\S]*?scrollbar-width: none;[\s\S]*?\}/,
  );
  expect(utilitiesSource).toMatch(
    /\.scrollbar-none::-webkit-scrollbar \{[\s\S]*?display: none;[\s\S]*?\}/,
  );
});
