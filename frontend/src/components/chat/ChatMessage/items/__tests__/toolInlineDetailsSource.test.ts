import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
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

test("tool inline preview details share the indented natural-height container", () => {
  const source = readSource("../ToolInlineDetails.tsx");

  expect(source).toMatch(/export function ToolInlineDetails/);
  expect(source).toMatch(/className="tool-inline-details"/);
  expect(componentsCss).toMatch(/\.tool-inline-details\s*\{/);
  expect(componentsCss).toMatch(/margin-top:\s*0\.5rem/);
  expect(componentsCss).toMatch(/margin-left:\s*1rem/);
  expect(componentsCss).toMatch(/padding-left:\s*0\.75rem/);
  expect(componentsCss).toMatch(/border-left:\s*2px solid/);
  expect(componentsCss).not.toMatch(
    /\.tool-inline-details\s*\{[\s\S]*max-height:/,
  );
  expect(componentsCss).not.toMatch(
    /\.tool-inline-details\s*\{[\s\S]*overflow-y:\s*auto/,
  );
  expect(componentsCss).toMatch(/overflow-x:\s*auto/);
  expect(componentsCss).toMatch(/min-width:\s*0/);

  for (const relativePath of inlineConsumers) {
    const consumer = readSource(relativePath);

    expect(consumer).toMatch(
      /import \{ ToolInlineDetails \} from "\.\/ToolInlineDetails"/,
    );
    expect(consumer).toMatch(/<ToolInlineDetails>/);
    expect(consumer).not.toMatch(
      /mt-2 ml-4 pl-3 border-l-2 border-theme-border max-h-80 overflow-y-auto overflow-x-hidden min-w-0/,
    );
  }
});
