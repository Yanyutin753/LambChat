import { readFileSync } from "node:fs";
import { expect, test } from "vitest";

test("capped errors start at the top so their first lines remain reachable", () => {
  const source = readFileSync(
    new URL("../ConfigPanelErrorCallout.tsx", import.meta.url),
    "utf8",
  );
  expect(source).toContain("items-start");
  expect(source).not.toContain("items-center");
  expect(source).toContain("[overflow-wrap:anywhere]");
});
