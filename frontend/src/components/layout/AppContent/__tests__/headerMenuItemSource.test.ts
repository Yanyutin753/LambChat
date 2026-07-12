import { readFileSync } from "node:fs";
const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("header overflow menu shares item and icon wrappers", () => {
  expect(source).toMatch(/function HeaderMenuItem\(/);
  expect(source).toMatch(/function HeaderMenuIcon\(/);
  expect(source).toMatch(
    /className="flex w-full items-center gap-3 px-3 py-2\.5 text-left text-sm transition-colors text-\[var\(--theme-text-secondary\)\] hover:text-\[var\(--theme-text\)\] hover:bg-\[var\(--theme-bg-subtle\)\]"/,
  );
  expect(source).toMatch(
    /className="flex items-center justify-center w-5 shrink-0"/,
  );

  expect(
    source.match(
      /flex w-full items-center gap-3 px-3 py-2\.5 text-left text-sm transition-colors text-\[var\(--theme-text-secondary\)\] hover:text-\[var\(--theme-text\)\] hover:bg-\[var\(--theme-bg-subtle\)\]/g,
    )?.length,
  ).toBe(1);
  expect(
    source.match(/flex items-center justify-center w-5 shrink-0/g)?.length,
  ).toBe(1);
});
