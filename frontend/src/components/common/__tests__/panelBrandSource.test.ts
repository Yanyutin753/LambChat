import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

const source = (path: string) => readFileSync(`src/${path}`, "utf8");

test("skill cards retain original serif headings and shared controls retain theme focus", () => {
  for (const name of ["SkillBaseCard"]) {
    expect(source(`components/common/${name}.tsx`)).toContain("font-serif");
  }
  const css = source("styles/components.css");
  expect(css).toMatch(/\.panel-header \{[^}]*margin-bottom: 0.75rem;/);
  expect(css).toMatch(/\.panel-pagination \{[^}]*margin-top: 0;/);
  expect(css).toMatch(
    /\.btn-secondary:focus-visible \{[^}]*var\(--theme-ring\)/,
  );
  expect(css).not.toMatch(/\.dark \.btn-primary \{[^}]*#1c1917/);
  expect(source("components/common/ConfirmDialog.tsx")).toContain(
    "text-theme-warning",
  );
});
