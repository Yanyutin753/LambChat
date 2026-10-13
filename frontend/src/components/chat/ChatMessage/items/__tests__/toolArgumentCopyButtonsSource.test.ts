import { readFileSync, readdirSync } from "node:fs";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));
const itemsDir = resolve(__dirname, "..");

function readSource(path: string): string {
  return readFileSync(resolve(__dirname, path), "utf8");
}

test("tool item argument and summary blocks do not render floating copy buttons", () => {
  const offenders: string[] = [];

  for (const entry of readdirSync(itemsDir)) {
    if (extname(entry) !== ".tsx") continue;
    if (entry === "ToolHoverCopyButton.tsx") continue;

    const source = readFileSync(resolve(itemsDir, entry), "utf8");
    if (/position="args(?:Compact)?"/.test(source)) {
      offenders.push(entry);
    }
  }

  expect(offenders).toEqual([]);
});

test("generic tool call argument sections do not expose copy actions", () => {
  const source = readSource("../../ToolCallItem.tsx");

  expect(source).not.toMatch(/action=\{<CopyButton text=\{argsJson\}/);
});

test("every shared tool argument block supplies full copy text", () => {
  const offenders: string[] = [];
  for (const entry of readdirSync(itemsDir)) {
    if (extname(entry) !== ".tsx") continue;
    const source = readFileSync(resolve(itemsDir, entry), "utf8");
    for (const block of source.matchAll(/<ToolArgsBlock\b[^>]*>/g)) {
      if (!/copyText=\{/.test(block[0])) offenders.push(entry);
      expect(block[0]).not.toMatch(/copyText=\{(?:truncate\(|[^}]*\.slice\()/);
    }
  }
  expect(offenders).toEqual([]);
});
