import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("fixed landing navigation leaves room for the native titlebar", () => {
  const source = readFileSync(
    "src/components/landing/components/Navbar.tsx",
    "utf8",
  );
  expect(source).toContain('top: "var(--titlebar-inset, 0px)"');
  expect(source).not.toContain("fixed top-0");
});

test("mobile menu follows the navbar below the native titlebar", () => {
  const css = readFileSync("src/styles/landing.css", "utf8");
  expect(css).toMatch(
    /\.landing-mobile-menu\s*\{\s*top:\s*calc\(72px \+ var\(--app-safe-area-top, 0px\) \+ var\(--titlebar-inset, 0px\)\)/,
  );
});
