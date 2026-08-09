import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("subagent auto-open uses keyed state and the shared empty-lane gate", () => {
  const source = readFileSync(
    new URL("../SubagentBlock.tsx", import.meta.url),
    "utf8",
  );

  expect(source).toMatch(/hasOpenRightPanel/);
  expect(source).toMatch(/shouldAllowAutomaticRightPanel/);
  expect(source).toMatch(/hasSubagentPanelAutoOpened\(panelKey\)/);
  expect(source).toMatch(
    /markSubagentPanelAutoOpened\(panelKey\)[\s\S]*openPersistentToolPanel/,
  );
  expect(source).toMatch(/auto:\s*true/);
});

test("external navigation imports the subagent opener without a barrel cycle", () => {
  const source = readFileSync(
    new URL(
      "../../../layout/AppContent/useMessageScroll.externalNavigation.ts",
      import.meta.url,
    ),
    "utf8",
  );

  expect(source).toMatch(/from "\.\.\/\.\.\/chat\/ChatMessage\/SubagentBlock"/);
  expect(source).not.toMatch(
    /from "\.\.\/\.\.\/chat\/ChatMessage\/SubagentBlocks"/,
  );
});
