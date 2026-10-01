import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../FeedbackPanel.tsx", import.meta.url),
  "utf8",
);

test("feedback filters share the title row without a second inset", () => {
  expect(source).toMatch(/actions=\{[\s\S]*?<FilterTabs/);
  expect(source).toContain('className="panel-header--section-switch"');
  expect(source).toContain(
    'className="feedback-filter-tabs flex items-center gap-1"',
  );
  expect(source).toContain("aria-pressed={isActive}");
});
