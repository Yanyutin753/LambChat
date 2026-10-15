import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../ModelSelector.tsx", import.meta.url), {
  encoding: "utf8",
});

test("model selector trigger uses shared header typography and theme colors", () => {
  expect(source).toMatch(
    /className="flex items-center gap-1\.5 rounded-lg text-theme-text-secondary hover:bg-theme-bg-subtle hover:text-theme-text transition-colors"/,
  );
  expect(source).toMatch(
    /className="text-14 leading-5 font-medium font-serif !font-serif max-w-\[200px\] truncate"/,
  );
  expect(source).toMatch(/className=\{`transition-transform duration-200 \$\{/);
  expect(source).not.toMatch(/text-\[var\(--theme-text-secondary\)\]/);
  expect(source).not.toMatch(/text-\[var\(--color-text-secondary\)\]/);
  expect(source).not.toMatch(/text-stone-400 dark:text-stone-300/);
});
