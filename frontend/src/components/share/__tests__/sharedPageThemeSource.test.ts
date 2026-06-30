import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const sharedPageSource = readFileSync(
  join(import.meta.dirname, "../SharedPage.tsx"),
  "utf8",
);

test("shared page top-level surfaces use theme tokens for light and dark modes", () => {
  assert.match(
    sharedPageSource,
    /min-h-dvh bg-theme-bg text-theme-text flex items-center justify-center/,
  );
  assert.match(
    sharedPageSource,
    /flex flex-col bg-theme-bg text-theme-text min-h-dvh font-sans border-r border-theme-border/,
  );
  assert.match(sharedPageSource, /border-b border-theme-border/);
  assert.match(
    sharedPageSource,
    /bg-\[color-mix\(in_srgb,var\(--theme-bg-card\)_82%,transparent\)\]/,
  );
  assert.match(
    sharedPageSource,
    /max-w-6xl mx-auto px-4 sm:px-8 h-14 flex items-center justify-between/,
  );
  assert.match(sharedPageSource, /bg-theme-bg-card rounded-2xl/);
  assert.match(sharedPageSource, /border border-theme-border/);
  assert.doesNotMatch(sharedPageSource, /bg-\[#faf9f7\]/);
  assert.doesNotMatch(sharedPageSource, /dark:bg-\[#0f0e0d\]/);
});
