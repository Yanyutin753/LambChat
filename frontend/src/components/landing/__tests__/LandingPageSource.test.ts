import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../LandingPage.tsx", import.meta.url),
  "utf8",
);

test("landing page root container applies font-serif to all page text", () => {
  expect(source).toMatch(
    /className="blog-landing-container[^\n]*\bfont-serif\b/,
  );
});

test("landing page gates marketing content behind the auto-login splash", () => {
  // Returning users hold a token while auth resolves — show the splash
  // instead of mounting (and flashing) the full marketing page.
  expect(source).toMatch(/shouldShowAutoLoginSplash\(\{/);
  expect(source).toMatch(/return\s+<AutoLoginSplash\s*\/>/);
  // The gate must come after every hook call so hook order stays stable.
  const gateIndex = source.indexOf("shouldShowAutoLoginSplash({");
  const lastHookIndex = source.lastIndexOf("useCallback(");
  expect(gateIndex).toBeGreaterThan(lastHookIndex);
});
