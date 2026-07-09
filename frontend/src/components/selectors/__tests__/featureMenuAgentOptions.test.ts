import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../FeatureMenu.tsx", import.meta.url),
  "utf8",
);

test("feature menu no longer renders boolean agent options (moved to RunModePopover)", () => {
  // The settings group with boolean agent options was moved to RunModePopover
  // (right-side toolbar). FeatureMenu now only contains enhance and upload groups.
  expect(source).not.toMatch(/booleanOptionEntries/);
  expect(source).not.toMatch(/onToggleAgentOption/);
  expect(source).not.toMatch(/hasThinkingOption/);
});
