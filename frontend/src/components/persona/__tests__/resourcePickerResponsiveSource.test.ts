import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const css = readFileSync(
  new URL("../../../styles/persona.css", import.meta.url),
  "utf8",
);
const utilities = readFileSync(
  new URL("../../../styles/utilities.css", import.meta.url),
  "utf8",
);
const selector = readFileSync(
  new URL("../PersonaPresetSelector.tsx", import.meta.url),
  "utf8",
);
test("translated card actions can wrap within a narrow phone card", () => {
  expect(selector).toMatch(/mt-4 flex flex-wrap items-center/);
  expect(css).toMatch(
    /\.resource-picker \.pps-card__action\s*\{[^}]*max-width:\s*100%;/,
  );
});

test("shared card grids can shrink below the desktop minimum track width", () => {
  expect(utilities).toMatch(/minmax\(min\(100%,\s*320px\),\s*1fr\)/);
});
test("picker cards fit the available mobile body and touch controls keep 44px targets", () => {
  expect(css).toMatch(/\.pps-card\s*\{[^}]*min-width:\s*0;/);
  expect(css).toMatch(/\.resource-picker[^}]*min-height:\s*2\.75rem;/);
  expect(css).toMatch(/\.resource-picker[^}]*font-size:\s*1rem;/);
  expect(css).toMatch(/@media \(max-width: 639px\), \(pointer: coarse\)/);
});

test("picker animation and hover movement respect reduced motion", () => {
  expect(css).toMatch(
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.pps-card[^}]*animation:\s*none;/,
  );
  expect(css).toMatch(
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.pps-card:hover[^}]*transform:\s*none;/,
  );
});
