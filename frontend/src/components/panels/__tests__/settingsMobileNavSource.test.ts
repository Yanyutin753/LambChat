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

test("mobile category nav is a horizontally scrollable chip tab strip", () => {
  expect(panelSource).toMatch(
    /className="[^"]*sm:hidden[^"]*"[\s\S]*?className="flex gap-1 overflow-x-auto scrollbar-none scroll-smooth/,
  );
  expect(panelSource).toMatch(/scrollSnapType: "x mandatory"/);
  expect(panelSource).toMatch(/scrollSnapAlign: "start"/);
  expect(panelSource).toMatch(/shrink-0/);
  expect(panelSource).toMatch(/whitespace-nowrap/);
});

test("mobile category chips no longer use a Select dropdown", () => {
  expect(panelSource).not.toMatch(/<Select[\s\S]{0,120}value=\{activeCategory\}/);
});

test("active category chip scrolls into view on mobile", () => {
  expect(panelSource).toMatch(/activeCategoryTabRef/);
  expect(panelSource).toMatch(
    /scrollTo\(\{\s*left: Math\.max\(0, target\),\s*behavior: "instant",?\s*\}\)/,
  );
});

test("desktop sidebar and mobile chips share the visible category list", () => {
  expect(panelSource).toMatch(/visibleCategories/);
  expect(panelSource).toMatch(/visibleCategories\.map/);
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
