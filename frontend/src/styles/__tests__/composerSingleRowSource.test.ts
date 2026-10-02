import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const css = readFileSync(new URL("../desktop.css", import.meta.url), "utf8");
test("wide composer stays on one row and narrow columns can wrap actions", () => {
  expect(css).toMatch(/flex-wrap:\s*nowrap/);
  expect(css).toMatch(
    /@container composer \(max-width: 320px\)[\s\S]*flex-wrap:\s*wrap/,
  );
  expect(css).toMatch(/container-type:\s*inline-size/);
  expect(css).toMatch(/@container composer[^}]+composer-sandbox-label/s);
  expect(css).toMatch(/@container composer[^}]+composer-usage-amount/s);
});
