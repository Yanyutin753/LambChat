import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const __dirname = dirname(fileURLToPath(import.meta.url));

function readSource(relativePath: string): string {
  return readFileSync(resolve(__dirname, relativePath), "utf8");
}

test("memory recall query summary does not render a floating copy button", () => {
  const source = readSource("../MemoryRecallItem.tsx");
  const querySummaryStart = source.indexOf("{/* Query summary header */}");
  const memoryCardsStart = source.indexOf("{/* Memory cards */}");

  expect(querySummaryStart).not.toBe(-1);
  expect(memoryCardsStart).not.toBe(-1);
  expect(memoryCardsStart > querySummaryStart).toBeTruthy();

  const querySummarySource = source.slice(querySummaryStart, memoryCardsStart);

  expect(querySummarySource).not.toMatch(/<ToolHoverCopyButton\b/);
});
