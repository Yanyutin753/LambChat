import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

const argsBlockConsumers = [
  "../EditFileItem.tsx",
  "../GlobItem.tsx",
  "../GrepItem.tsx",
  "../LsItem.tsx",
  "../ReadFileItem.tsx",
  "../WriteFileItem.tsx",
];

test("tool argument blocks share detail and compact wrappers", () => {
  const source = readSource("../ToolArgsBlock.tsx");

  expect(source).toMatch(/type ToolArgsBlockSize = "detail" \| "compact"/);
  expect(source).toMatch(
    /detail:\s*"tool-args-block group\/args relative flex items-center gap-2 px-3 py-2 rounded-\[var\(--radius-sm\)\] bg-theme-bg-card text-14 text-theme-text-secondary font-mono/,
  );
  expect(source).toMatch(
    /compact:\s*"tool-args-block group\/args relative flex items-center gap-2 mb-2 px-2 py-1\.5 rounded-\[var\(--radius-sm\)\] bg-theme-bg-card text-12 text-theme-text-secondary font-mono/,
  );
  expect(source).toMatch(/wrap \? "tool-args-block__content--wrap" : ""/);
  expect(source).toMatch(/copyText: string/);
  expect(source).toMatch(
    /min-w-0 flex-1 flex items-center gap-2 overflow-x-auto/,
  );
  expect(source).not.toMatch(/sm:opacity-0/);

  for (const relativePath of argsBlockConsumers) {
    const consumer = readSource(relativePath);

    expect(consumer).toMatch(
      /import \{ ToolArgsBlock \} from "\.\/ToolArgsBlock"/,
    );
    expect(consumer).toMatch(/<ToolArgsBlock\s+size="detail"/);
    expect(consumer).toMatch(/<ToolArgsBlock\s+size="compact"/);
    expect(consumer).not.toMatch(
      /group\/args relative flex items-center gap-2 (?:mb-2 )?px-(?:3 py-2 rounded-\[var|2 py-1\.5 rounded-\[var).*bg-white dark:bg-\[var\(--theme-bg-card\)\].*text-(?:sm|xs) text-theme-text-tertiary font-mono/,
    );
  }
});

test("tool argument layout stays within narrow grids and preserves touch targets", () => {
  const source = readSource("../ToolArgsBlock.tsx");
  const css = readSource("../../../../../styles/components.css");
  expect(source).toMatch(/data-size=\{size\}/);
  expect(source).toMatch(/tool-args-block__copy/);
  expect(css).toMatch(
    /\.tool-args-block\s*\{[^}]*min-width:\s*0;[^}]*max-width:\s*100%/,
  );
  expect(css).toMatch(
    /\.tool-args-block__content--wrap\s*\{[^}]*display:\s*block/,
  );
  expect(css).toMatch(
    /\.tool-args-block\[data-size="compact"\] \.tool-args-block__copy\s*\{[^}]*width:\s*1\.5rem;[^}]*height:\s*1\.5rem/,
  );
  expect(css).toMatch(
    /@media[^}]*\.tool-args-block[^}]*\.tool-args-block__copy[^}]*width:\s*2\.25rem;[^}]*height:\s*2\.25rem/,
  );
});

test("right panel code arguments retain the shared monospace font", () => {
  const css = readSource("../../../../../styles/components.css");
  expect(css).toMatch(
    /\.tool-readable \.tool-args-block__content \.font-mono\s*\{\s*font-family: theme\(['"]fontFamily\.mono['"]\);/,
  );
});
