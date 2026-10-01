import { readFileSync } from "node:fs";

test("shared card motion is disabled outside panels too when reduced motion is requested", () => {
  const css = readFileSync(
    new URL("../card-base.css", import.meta.url),
    "utf8",
  );
  expect(css).toMatch(
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.scb,[\s\S]*?\.mp-card\s*\{[\s\S]*?animation:\s*none/,
  );
});
