import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

test("ToolSearchItem renders parsed tool cards with summary counts", () => {
  const source = readSource("../ToolSearchItem.tsx");
  expect(source).toMatch(/parseToolSearchResult/);
  expect(source).toMatch(/toolSearchToolCount/);
  expect(source).toMatch(/toolSearchNewlyLoaded/);
  expect(source).toMatch(/toolSearchAlreadyAvailable/);
  expect(source).toMatch(/formatLabel=\{false\}/);
});

test("GrepItem pill label appends matched file count", () => {
  const source = readSource("../GrepItem.tsx");
  expect(source).toMatch(/\(\$\{parsedResult\.files\.length\}\)/);
});

test("GlobItem shows result counts in pill, inline list, and panel", () => {
  const source = readSource("../GlobItem.tsx");
  expect(source).toMatch(/\(\$\{paths\.length\}\)/);
  expect(source).toMatch(/toolFileCount/);
  expect(source).toMatch(/paths\.slice\(0, 10\)/);
  expect(source).toMatch(/toolMoreFiles/);
});

test("LsItem pill label appends entry count", () => {
  const source = readSource("../LsItem.tsx");
  expect(source).toMatch(/toolItemCount[^\n]*entries\.length/);
  // pill label itself must include the count, not only the panel args block
  expect(source).toMatch(
    /label=\{`\$\{t\("chat\.message\.toolLs"\)\} \$\{dirPath\}\$\{pillCount\}`\}/,
  );
});

test("ConversationHistoryItem panel shows session and turn count headers", () => {
  const source = readSource("../ConversationHistoryItem.tsx");
  expect(source).toMatch(/toolHistorySessionCount/);
  expect(source).toMatch(/toolHistoryTurnCount/);
});

test("entity-specific more-keys replace generic toolMoreFiles", () => {
  expect(readSource("../MemoryRecallItem.tsx")).toMatch(/toolMoreMemories/);
  expect(readSource("../ImageAnalyzeItem.tsx")).toMatch(/toolMoreImages/);
  expect(readSource("../ScheduledTaskItem.tsx")).toMatch(/toolMoreTasks/);
});
