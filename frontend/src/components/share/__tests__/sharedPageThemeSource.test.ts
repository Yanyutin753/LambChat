import { readFileSync } from "node:fs";
import { join } from "node:path";

const sharedPageSource = readFileSync(
  join(import.meta.dirname, "../SharedPage.tsx"),
  "utf8",
);

test("shared page top-level surfaces use theme tokens for light and dark modes", () => {
  expect(sharedPageSource).toMatch(
    /min-h-dvh bg-theme-bg text-theme-text flex items-center justify-center/,
  );
  expect(sharedPageSource).toMatch(
    /flex flex-col bg-theme-bg text-theme-text min-h-dvh font-sans border-r border-theme-border/,
  );
  expect(sharedPageSource).toMatch(/border-b border-theme-border/);
  expect(sharedPageSource).toMatch(
    /bg-\[color-mix\(in_srgb,var\(--theme-bg-card\)_82%,transparent\)\]/,
  );
  expect(sharedPageSource).toMatch(
    /max-w-6xl mx-auto px-4 sm:px-8 h-14 flex items-center justify-between/,
  );
  expect(sharedPageSource).toMatch(/bg-theme-bg-card rounded-2xl/);
  expect(sharedPageSource).toMatch(/border border-theme-border/);
  expect(sharedPageSource).not.toMatch(/bg-\[#faf9f7\]/);
  expect(sharedPageSource).not.toMatch(/dark:bg-\[#0f0e0d\]/);
});
