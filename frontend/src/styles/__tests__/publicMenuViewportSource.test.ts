import { readFileSync } from "node:fs";
test("public mobile navigation scrolls inside short viewports", () => {
  const css = readFileSync(new URL("../landing.css", import.meta.url), "utf8");
  expect(css).toMatch(
    /\.landing-mobile-menu\s*\{[^}]*max-height:\s*calc\(100dvh[^}]*overflow-y:\s*auto;/,
  );
});
