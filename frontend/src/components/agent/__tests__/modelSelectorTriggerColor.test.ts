import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../ModelSelector.tsx", import.meta.url), {
  encoding: "utf8",
});
const styles = readFileSync(
  new URL("../../../styles/components.css", import.meta.url),
  "utf8",
);

test("model selector trigger uses shared header typography and theme colors without hover styles", () => {
  expect(source).toMatch(
    /className="flex items-center gap-1\.5 rounded-lg text-theme-text-secondary"/,
  );
  expect(source).toMatch(
    /className="text-14 leading-5 font-medium font-serif !font-serif max-w-\[200px\] truncate"/,
  );
  expect(source).toMatch(
    /className=\{`transition-transform duration-200 motion-reduce:transition-none \$\{/,
  );
  expect(source).not.toMatch(/text-\[var\(--theme-text-secondary\)\]/);
  expect(source).not.toMatch(/text-\[var\(--color-text-secondary\)\]/);
  expect(source).not.toMatch(/text-stone-400 dark:text-stone-300/);
});

test("shared header hover styles exclude the model selector trigger", () => {
  expect(source).toMatch(
    /<button\s+data-model-selector-trigger\s+onClick=\{toggleSelector\}/,
  );
  expect(styles.replace(/\s+/g, "")).toContain(
    '.chat-header__identity>.relative>button:not([data-model-selector-trigger]):is(:hover,[aria-expanded="true"])',
  );
  expect(styles.replace(/\s+/g, "")).not.toContain(
    '.chat-header__identity>.relative>button:is(:hover,[aria-expanded="true"])',
  );
});
