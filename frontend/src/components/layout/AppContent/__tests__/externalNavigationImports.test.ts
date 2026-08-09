import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

test("external navigation imports the subagent opener from its defining module", () => {
  const source = readFileSync(
    resolve(import.meta.dirname, "../useMessageScroll.externalNavigation.ts"),
    "utf8",
  );

  expect(source).toMatch(/from "\.\.\/\.\.\/chat\/ChatMessage\/SubagentBlock"/);
  expect(source).not.toMatch(/ChatMessage\/SubagentBlocks/);
});
