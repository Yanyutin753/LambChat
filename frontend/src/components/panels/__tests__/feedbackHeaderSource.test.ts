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

const skeletons = readFileSync(
  new URL("../../skeletons/InfraSkeletons.tsx", import.meta.url),
  "utf8",
);

test("feedback rows and loading rows share responsive alignment", () => {
  for (const markup of [source, skeletons]) {
    expect(markup).toContain('className="feedback-row panel-inset"');
    expect(markup).toContain('className="feedback-row__header"');
    expect(markup).toContain('className="feedback-row__meta"');
    expect(markup).toContain('className="feedback-row__actions"');
  }
  expect(source).not.toContain("panel-inset px-4 sm:px-6");
});

test("initial feedback loading reserves summary and filter geometry", () => {
  expect(source).toContain("<FeedbackSummarySkeleton />");
  expect(source).toContain("<FeedbackFiltersSkeleton />");
  expect(skeletons).toContain('className="feedback-summary panel-summary"');
});
