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
    /panel:\s*"absolute top-2 right-2 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"/,
  );
  expect(source).toMatch(
    /panelRaised:\s*"absolute top-2 right-2 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity z-10"/,
  );
  expect(source).toMatch(
    /panelCompact:\s*"absolute top-1 right-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"/,
  );
  expect(source).toMatch(
    /panelCompactRaised:\s*"absolute top-1 right-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity z-10"/,
  );
  expect(source).toMatch(
    /result:\s*"absolute top-1\.5 right-1\.5 sm:opacity-0 sm:group-hover\/result:opacity-100 transition-opacity"/,
  );
  expect(source).toMatch(
    /resultCompact:\s*"absolute top-0\.5 right-0\.5 transition-opacity"/,
  );
  expect(source).toMatch(/<CopyButton/);

  for (const relativePath of formerArgsCopyConsumers) {
    const consumer = readSource(relativePath);

    expect(consumer).not.toMatch(/position="args(?:Compact)?"/);
    expect(consumer).not.toMatch(
      /absolute top-(?:1\.5|0\.5|2|1) right-(?:1\.5|0\.5|2|1) sm:opacity-0 sm:group-hover(?:\/args|\/result)?:opacity-100 transition-opacity(?: z-10)?/,
    );
  }
});
