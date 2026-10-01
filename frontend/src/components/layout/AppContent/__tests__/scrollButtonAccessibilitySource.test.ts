import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = readFileSync(
  new URL("../ChatView.tsx", import.meta.url),
  "utf8",
);
test("chat scroll controls are named and hidden controls leave keyboard navigation", () => {
  expect(source).toMatch(/aria-label=\{t\("common\.scrollToTop"\)\}/);
  expect(source).toMatch(/aria-label=\{t\("common\.scrollToBottom"\)\}/);
  expect(source).toMatch(/disabled=\{isNearTop\}/);
  expect(source).toMatch(/disabled=\{isNearBottom\}/);
  expect(source).toMatch(/aria-hidden=\{isNearTop\}/);
  expect(source).toMatch(/aria-hidden=\{isNearBottom\}/);
});
