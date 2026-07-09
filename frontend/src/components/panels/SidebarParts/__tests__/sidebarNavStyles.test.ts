import { readFileSync } from "node:fs";
const baseCss = readFileSync(
  new URL("../../../../styles/base.css", import.meta.url),
  "utf8",
);

test("sidebar icon labels share one nav text style", () => {
  const navButtonRule = baseCss.match(/\.sidebar-nav-btn\s*\{[\s\S]*?\}/)?.[0];

  expect(navButtonRule).toBeTruthy();
  expect(navButtonRule).toMatch(/font-size:\s*0\.875rem;/);
  expect(navButtonRule).toMatch(/line-height:\s*1\.25rem;/);
  expect(navButtonRule).toMatch(/font-weight:\s*500;/);
});
