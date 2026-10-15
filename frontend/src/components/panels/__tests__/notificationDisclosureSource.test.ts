import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
const source = readFileSync(
  new URL("../NotificationPanel.tsx", import.meta.url),
  "utf8",
);
test("collapsed notifications reserve no detail padding and hide content from assistive technology", () => {
  expect(source).toContain('isExpanded ? "pb-3 pt-2" : ""');
  expect(source).toContain("aria-expanded={isExpanded}");
  expect(source).toContain("aria-hidden={!isExpanded}");
  expect(source).toContain("inert={!isExpanded}");
  expect(source).toContain("max-h-96 overflow-y-auto opacity-100");
  expect(source).toContain("motion-reduce:transition-none");
});
