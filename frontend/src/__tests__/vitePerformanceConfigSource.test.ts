import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

const source = readFileSync(
  resolve(import.meta.dirname, "../../vite.config.ts"),
  "utf8",
);

test("Vite enforces eager JavaScript and precache budgets", () => {
  expect(source).toMatch(/manifest:\s*true/);
  expect(source).toMatch(/manifestTransforms/);
  expect(source).toMatch(/createPerformanceManifestTransform/);
  expect(source).toMatch(/EAGER_JAVASCRIPT_BUDGET_BYTES/);
  expect(source).toMatch(/PRECACHE_BUDGET_BYTES/);
});

test("optional editors, sandboxes, and diagrams are not promoted into manual chunks", () => {
  expect(source).not.toMatch(/"vendor-mermaid":\s*\["mermaid"\]/);
  expect(source).not.toMatch(/"vendor-codemirror":/);
  expect(source).not.toMatch(/"vendor-sandpack":/);
});
