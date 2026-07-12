import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../Header.tsx", import.meta.url), "utf8");

test("mobile sidebar expand toggle matches the sidebar collapse icon color", () => {
  expect(source).toMatch(
    /className=\{`flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-\[var\(--color-background-muted\)\] dark:text-stone-300 sm:hidden transition-colors`\}/,
  );
  expect(source).toMatch(/className="w-5 h-5"/);
  expect(source).not.toMatch(
    /className="w-5 h-5 text-\[var\(--color-text-secondary\)\]"/,
  );
});

test("header overflow menu trigger matches the sidebar collapse icon color", () => {
  expect(source).toMatch(
    /className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-\[var\(--color-background-muted\)\] dark:text-stone-300 transition-colors"\s+title=\{t\("common\.menu"\)\}/,
  );
});
