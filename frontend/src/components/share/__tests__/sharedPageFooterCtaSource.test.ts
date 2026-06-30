import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const sharedPageSource = readFileSync(
  join(import.meta.dirname, "../SharedPage.tsx"),
  "utf8",
);

test("shared page footer CTA keeps a simple branded banner treatment", () => {
  assert.match(sharedPageSource, /data-share-footer-cta/);
  assert.match(sharedPageSource, /aria-label=\{t\("share\.createYourOwn"\)\}/);
  assert.match(
    sharedPageSource,
    /bg-\[color-mix\(in_srgb,var\(--theme-bg-card\)_82%,transparent\)\] shadow-sm/,
  );
  assert.match(sharedPageSource, /min-h-11/);
  assert.match(sharedPageSource, /BrandLogo className="size-6"/);
  assert.match(sharedPageSource, /group-hover:translate-x-1/);
});
