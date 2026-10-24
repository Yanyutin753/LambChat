import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

const formerArgsCopyConsumers = [
  "../EditFileItem.tsx",
  "../ExecuteItem.tsx",
  "../GlobItem.tsx",
  "../GrepItem.tsx",
  "../LsItem.tsx",
  "../McpBlockPreview.tsx",
  "../ReadFileItem.tsx",
  "../WriteFileItem.tsx",
];

test("tool hover copy controls are reserved for result and content blocks", () => {
  const source = readSource("../ToolHoverCopyButton.tsx");

  expect(source).toMatch(
    /type ToolHoverCopyPosition =[\s\S]*"panel"[\s\S]*"panelRaised"[\s\S]*"panelCompact"[\s\S]*"panelCompactRaised"[\s\S]*"result"[\s\S]*"resultCompact"/,
  );
  expect(source).not.toMatch(/"args(?:Compact)?"/);
  expect(source).not.toMatch(/group-hover\/args/);
  expect(source).toMatch(
    /panel:\s*"absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"/,
  );
  expect(source).toMatch(
    /panelRaised:\s*"absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity z-10"/,
  );
  expect(source).toMatch(
    /panelCompact:\s*"absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity"/,
  );
  expect(source).toMatch(
    /panelCompactRaised:\s*"absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity z-10"/,
  );
  expect(source).toMatch(
    /result:\s*"absolute top-1\.5 right-1\.5 opacity-0 group-hover\/result:opacity-100 transition-opacity"/,
  );
  expect(source).toMatch(
    /resultCompact:\s*"absolute top-0\.5 right-0\.5 opacity-0 group-hover\/result:opacity-100 transition-opacity"/,
  );
  expect(source).toMatch(/<CopyButton/);
  expect(source).toContain("focus-within:opacity-100");
  expect(source).toContain("pointer-events-none");
  expect(source).toContain("motion-reduce:transition-none");

  for (const relativePath of formerArgsCopyConsumers) {
    const consumer = readSource(relativePath);

    expect(consumer).not.toMatch(/position="args(?:Compact)?"/);
    expect(consumer).not.toMatch(
      /absolute top-(?:1\.5|0\.5|2|1) right-(?:1\.5|0\.5|2|1) sm:opacity-0 sm:group-hover(?:\/args|\/result)?:opacity-100 transition-opacity(?: z-10)?/,
    );
  }
});

test("floating tool copies do not reserve a separate content column", () => {
  const css = readSource("../../../../../styles/components.css");
  expect(css).not.toMatch(
    /:has\(> \.tool-hover-copy > \.copy-button\)\s*\{[^}]*padding-inline-end/,
  );
  expect(css).toMatch(
    /@media \(hover: none\)\s*\{\s*\.tool-readable \.tool-hover-copy\s*\{\s*opacity: 1;\s*pointer-events: auto/,
  );
});

test("directory result names wrap instead of truncating available content", () => {
  const source = readSource("../LsItem.tsx");
  expect(source).toContain(
    '"min-w-0 flex-1 whitespace-normal [overflow-wrap:anywhere]"',
  );
  expect(source).not.toContain('"min-w-0 flex-1 truncate"');
});
