import { readFileSync } from "node:fs";
import { join } from "node:path";

const sharedPageSource = readFileSync(
  join(import.meta.dirname, "../SharedPage.tsx"),
  "utf8",
);

test("shared page footer CTA keeps a simple branded banner treatment", () => {
  expect(sharedPageSource).toMatch(/data-share-footer-cta/);
  expect(sharedPageSource).toMatch(
    /aria-label=\{t\("share\.createYourOwn"\)\}/,
  );
  expect(sharedPageSource).toMatch(
    /bg-\[color-mix\(in_srgb,var\(--theme-bg-card\)_82%,transparent\)\] shadow-sm/,
  );
  expect(sharedPageSource).toMatch(/min-h-11/);
  expect(sharedPageSource).toMatch(/BrandLogo className="size-6"/);
  expect(sharedPageSource).toMatch(/group-hover:translate-x-1/);
});
