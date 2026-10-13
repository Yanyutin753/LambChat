import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

for (const panel of ["MemoryPanel", "ScheduledTaskPanel"]) {
  test(`${panel} uses the shared resource card and action menu`, () => {
    const source = readFileSync(
      new URL(`../${panel}/index.tsx`, import.meta.url),
      "utf8",
    );
    expect(source).toMatch(/<SkillBaseCard/);
    expect(source).toMatch(/actions=\{/);
    expect(source).toMatch(/icon=\{/);
    expect(source).not.toContain("glass-card");
  });
}

test("help uses a compact desktop button while retaining its mobile target", () => {
  const css = readFileSync(
    new URL("../../../styles/base.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /\.chat-input-help-menu \.ui-icon-button\.ui-button--sm\s*\{\s*width: 1\.5rem;\s*height: 1\.5rem;\s*min-height: 1\.5rem;/,
  );
  expect(css).toMatch(
    /@media \(max-width: 639px\)[\s\S]*\.chat-input-help-menu[\s\S]*width: 2\.25rem;/,
  );
});
