import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const grid = readFileSync(
  new URL("../components/GridCard.tsx", import.meta.url),
  "utf8",
);
const list = readFileSync(
  new URL("../components/ListCard.tsx", import.meta.url),
  "utf8",
);

test.each([
  ["GridCard", grid],
  ["ListCard", list],
])("%s More button toggles the menu instead of only reopening it", (_name, source) => {
  expect(source).toContain("if (ctx.menu) ctx.hide(true);");
  expect(source).toContain("else ctx.show(e, file);");
  expect(source).toContain('aria-expanded={!!ctx.menu}');
});
