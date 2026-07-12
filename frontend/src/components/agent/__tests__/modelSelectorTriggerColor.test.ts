import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../ModelSelector.tsx", import.meta.url), {
  encoding: "utf8",
});

test("model selector trigger matches the sidebar collapse icon color", () => {
  expect(source).toMatch(
    /className="flex items-center gap-1\.5 text-stone-600 hover:opacity-70 dark:text-stone-300 transition-opacity"/,
  );
  expect(source).toMatch(
    /className="text-base font-semibold max-w-\[200px\] truncate"/,
  );
  expect(source).toMatch(/className=\{`transition-transform duration-200 \$\{/);
  expect(source).not.toMatch(/text-\[var\(--theme-text-secondary\)\]/);
  expect(source).not.toMatch(/text-\[var\(--color-text-secondary\)\]/);
  expect(source).not.toMatch(/text-stone-400 dark:text-stone-300/);
});
