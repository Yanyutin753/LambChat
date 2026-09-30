import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const css = readFileSync(
  new URL("../../../styles/components.css", import.meta.url),
  "utf8",
);

test("pagination keeps readable theme-aware selected text and summary", () => {
  expect(css).toMatch(
    /\.pagination-page-active\s*\{[^}]*color: var\(--theme-bg\);/,
  );
  const summaries = [...css.matchAll(/\.pagination-summary\s*\{([^}]*)\}/g)];
  expect(summaries).toHaveLength(1);
  expect(summaries[0][1]).toContain("color: var(--theme-text-secondary)");
});
