import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

test("subagent blocks defer the heavy panel renderer", () => {
  const blockSource = readFileSync(
    resolve(import.meta.dirname, "../SubagentBlock.tsx"),
    "utf8",
  );
  const deferredSource = readFileSync(
    resolve(import.meta.dirname, "../DeferredSubagentPanelContent.tsx"),
    "utf8",
  );

  expect(blockSource).toMatch(/from "\.\/DeferredSubagentPanelContent"/);
  expect(blockSource).not.toMatch(/from "\.\/SubagentPanelContent"/);
  expect(deferredSource).toMatch(
    /lazy\(\(\) =>\s*import\("\.\/SubagentPanelContent"\)/,
  );
  expect(deferredSource).toMatch(/<Suspense/);
});
