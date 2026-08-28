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
