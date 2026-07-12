import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../UserMessageBubble.tsx", import.meta.url),
  "utf8",
);

test("user message skill chips and text share the same inline flow", () => {
  expect(source).toMatch(/className="inline leading-relaxed/);
  expect(source).toMatch(/className="skill-chip-row align-baseline/);
  expect(source).not.toMatch(/className="skill-chip-row shrink-0"/);
  expect(source).not.toMatch(/flex-1/);
});
