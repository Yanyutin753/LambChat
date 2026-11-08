import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const read = (path: string) =>
  readFileSync(new URL(path, import.meta.url), "utf8");
test("usage charts choose columns from their container rather than viewport", () => {
  const panel = read("../../UsagePanel.tsx");
  const css = read("../../../../styles/components.css");
  expect(panel).toContain("usage-overview-grid");
  expect(panel).not.toContain("xl:grid-cols-[minmax(0,1.45fr)");
  expect(css).toContain("container: usage / inline-size");
  expect(css).toContain("@container usage (min-width: 1100px)");
  expect(css).toMatch(
    /\.usage-breakdown-grid\s*\{\s*grid-template-columns: minmax\(0, 1fr\);/,
  );
});
