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
