import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
test("composer stays on one row and adapts labels to container width", () => {
  expect(css).not.toMatch(/flex-wrap:\s*wrap/);
  expect(css).toMatch(/container-type:\s*inline-size/);
  expect(css).toMatch(/@container composer[^}]+composer-sandbox-label/s);
  expect(css).toMatch(/@container composer[^}]+composer-usage-amount/s);
});
