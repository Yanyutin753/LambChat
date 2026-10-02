import { readFileSync } from "node:fs";
const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("header overflow and languages reuse the shared menu owner", () => {
  expect(source).toMatch(/<ResourceCardMenu/);
  expect(source).not.toMatch(/function HeaderMenuItem\(/);
  expect(source).not.toMatch(/function HeaderMenuIcon\(/);
});
