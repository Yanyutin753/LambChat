import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../PanelSkeletonHelpers.tsx", import.meta.url),
  "utf8",
);

test("panel skeletons share the repeated pagination placeholder", () => {
  expect(source).toMatch(/function PanelPaginationSkeleton\(/);
  expect(source).toMatch(/className="panel-pagination"/);
  expect(source).toMatch(/className="pagination-wrapper"/);
  expect(source).toMatch(/pagination-range/);
  expect(source).toMatch(/pagination-position/);
  expect(source.match(/pagination-btn skeleton-line/g)?.length).toBe(2);
  expect(source).toMatch(/pagination-page skeleton-line/);
  expect(source).not.toMatch(/glass-divider|PanelPaginationVariant/);
});

test("panel skeletons share segmented tab placeholders", () => {
  expect(source).toMatch(/function PanelSegmentedTabsSkeleton\(/);
  // 真实分段页签容器带 font-sans（AgentSection / ModelSection），骨架同步
  expect(source).toMatch(
    /className="inline-grid grid-cols-2 rounded-lg border border-\[var\(--glass-border\)\] bg-\[var\(--glass-bg-subtle\)\] p-1 my-3 font-sans"/,
  );
  expect(source).toMatch(
    /panelSegmentedTabItemClass =\s*"flex items-center justify-center gap-2 rounded-md px-3 py-2"/,
  );

  expect(
    source.match(
      /inline-grid grid-cols-2 rounded-lg border border-\[var\(--glass-border\)\] bg-\[var\(--glass-bg-subtle\)\] p-1 my-3 font-sans/g,
    )?.length,
  ).toBe(1);
  expect(
    source.match(/flex items-center justify-center gap-2 rounded-md px-3 py-2/g)
      ?.length,
  ).toBe(1);
});

test("embedded loading states do not nest full panel skeletons", () => {
  const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
  expect(read("../../panels/SettingsPanel.tsx")).toMatch(/<SettingsListSkeleton \/>/);
  expect(read("../../panels/FeedbackPanel.tsx")).toMatch(/<FeedbackListSkeleton \/>/);
  expect(read("../../panels/MarketplacePanel.tsx")).toMatch(/<MarketplacePanelSkeleton embedded=\{embedded\}/);
});

test("persona initial loading uses its current card layout", () => {
  const source = readFileSync(new URL("../../persona/PersonaPlazaPanel.tsx", import.meta.url), "utf8");
  expect(source).toMatch(/return <PersonaPlazaSkeleton \/>/);
});
