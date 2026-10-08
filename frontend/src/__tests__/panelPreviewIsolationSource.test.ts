import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("preview component overrides do not replace shared imports during dependency scanning", () => {
  const source = readFileSync(new URL("../../scripts/panel-preview.ts", import.meta.url), "utf8");
  expect(source).toMatch(/resolveId\(source, importer, options\)\s*\{\s*if \(options\.scan\) return;/);
});
