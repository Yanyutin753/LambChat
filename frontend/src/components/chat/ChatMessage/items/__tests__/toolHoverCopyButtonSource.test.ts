import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

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

  assert.match(
    source,
    /type ToolHoverCopyPosition =[\s\S]*"panel"[\s\S]*"panelRaised"[\s\S]*"panelCompact"[\s\S]*"panelCompactRaised"[\s\S]*"result"[\s\S]*"resultCompact"/,
  );
  assert.doesNotMatch(source, /"args(?:Compact)?"/);
  assert.doesNotMatch(source, /group-hover\/args/);
  assert.match(
    source,
    /panel:\s*"absolute top-2 right-2 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"/,
  );
  assert.match(
    source,
    /panelRaised:\s*"absolute top-2 right-2 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity z-10"/,
  );
  assert.match(
    source,
    /panelCompact:\s*"absolute top-1 right-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity"/,
  );
  assert.match(
    source,
    /panelCompactRaised:\s*"absolute top-1 right-1 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity z-10"/,
  );
  assert.match(
    source,
    /result:\s*"absolute top-1\.5 right-1\.5 sm:opacity-0 sm:group-hover\/result:opacity-100 transition-opacity"/,
  );
  assert.match(
    source,
    /resultCompact:\s*"absolute top-0\.5 right-0\.5 transition-opacity"/,
  );
  assert.match(source, /<CopyButton/);

  for (const relativePath of formerArgsCopyConsumers) {
    const consumer = readSource(relativePath);

    assert.doesNotMatch(consumer, /position="args(?:Compact)?"/);
    assert.doesNotMatch(
      consumer,
      /absolute top-(?:1\.5|0\.5|2|1) right-(?:1\.5|0\.5|2|1) sm:opacity-0 sm:group-hover(?:\/args|\/result)?:opacity-100 transition-opacity(?: z-10)?/,
      `${relativePath} should not duplicate hover copy wrapper classes`,
    );
  }
});
