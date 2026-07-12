import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../PanelSkeletonHelpers.tsx", import.meta.url),
  "utf8",
);

test("panel skeletons share the repeated pagination placeholder", () => {
  expect(source).toMatch(/function PanelPaginationSkeleton\(/);
  expect(source).toMatch(/type PanelPaginationVariant =/);
  expect(source).toMatch(/default:\s*"glass-divider px-3 py-3 sm:px-4 mt-2"/);
  expect(source).toMatch(
    /transparent:\s*"glass-divider bg-transparent px-4 py-4 sm:px-6 mt-2"/,
  );
  expect(source).toMatch(
    /<div className="flex items-center justify-center gap-2">/,
  );

  expect(source.match(/skeleton-line size-8 rounded-lg/g)?.length).toBe(2);
  expect(source.match(/skeleton-line w-32 sm:w-36 h-3/g)?.length).toBe(1);
  expect(source).not.toMatch(/skeleton-line h-3 w-24/);
});

test("panel skeletons share segmented tab placeholders", () => {
  expect(source).toMatch(/function PanelSegmentedTabsSkeleton\(/);
  expect(source).toMatch(
    /className="inline-grid grid-cols-2 rounded-lg border border-\[var\(--glass-border\)\] bg-\[var\(--glass-bg-subtle\)\] p-1 my-3"/,
  );
  expect(source).toMatch(
    /panelSegmentedTabItemClass =\s*"flex items-center justify-center gap-2 rounded-md px-3 py-2"/,
  );

  expect(
    source.match(
      /inline-grid grid-cols-2 rounded-lg border border-\[var\(--glass-border\)\] bg-\[var\(--glass-bg-subtle\)\] p-1 my-3/g,
    )?.length,
  ).toBe(1);
  expect(
    source.match(/flex items-center justify-center gap-2 rounded-md px-3 py-2/g)
      ?.length,
  ).toBe(1);
});
