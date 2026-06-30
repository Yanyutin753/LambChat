import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

const componentsCss = readFileSync(
  resolve(__dirname, "../../../../../styles/components.css"),
  "utf8",
);

const inlineConsumers = [
  "../EditFileItem.tsx",
  "../GlobItem.tsx",
  "../GrepItem.tsx",
  "../LsItem.tsx",
  "../ReadFileItem.tsx",
  "../WriteFileItem.tsx",
];

test("tool inline preview details share the indented scroll container", () => {
  const source = readSource("../ToolInlineDetails.tsx");

  assert.match(source, /export function ToolInlineDetails/);
  assert.match(source, /className="tool-inline-details"/);
  assert.match(componentsCss, /\.tool-inline-details\s*\{/);
  assert.match(componentsCss, /margin-top:\s*0\.5rem/);
  assert.match(componentsCss, /margin-left:\s*1rem/);
  assert.match(componentsCss, /padding-left:\s*0\.75rem/);
  assert.match(componentsCss, /border-left:\s*2px solid/);
  assert.match(componentsCss, /max-height:\s*20rem/);
  assert.match(componentsCss, /overflow-y:\s*auto/);
  assert.match(componentsCss, /overflow-x:\s*hidden/);
  assert.match(componentsCss, /min-width:\s*0/);

  for (const relativePath of inlineConsumers) {
    const consumer = readSource(relativePath);

    assert.match(
      consumer,
      /import \{ ToolInlineDetails \} from "\.\/ToolInlineDetails"/,
      `${relativePath} should import ToolInlineDetails`,
    );
    assert.match(
      consumer,
      /<ToolInlineDetails>/,
      `${relativePath} should use ToolInlineDetails`,
    );
    assert.doesNotMatch(
      consumer,
      /mt-2 ml-4 pl-3 border-l-2 border-theme-border max-h-80 overflow-y-auto overflow-x-hidden min-w-0/,
      `${relativePath} should not duplicate inline details classes`,
    );
  }
});
