import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../SummaryItem.tsx", import.meta.url),
  "utf8",
);

test("summary item keeps the shared pill chrome and adds a light description", () => {
  expect(source).toMatch(/suffix=\{/);
  expect(source).toMatch(/chat\.message\.summaryDescription/);
  expect(source).toMatch(/font-mono/);
  expect(source).toMatch(/text-xs/);
  expect(source).toMatch(/leading-none/);
  expect(source).toMatch(/font-medium/);
  expect(source).not.toMatch(/text-emerald/);
  expect(source).not.toMatch(/opacity-70/);
  expect(source).not.toMatch(/text-\[9px\]/);
  expect(source).not.toMatch(/summaryPillClassName/);
  expect(source).not.toMatch(/className=\{summaryPillClassName\}/);
  expect(source).not.toMatch(/summaryPanelBodyClassName/);
  expect(source).not.toMatch(/hover:-translate-y-0\.5/);
});
