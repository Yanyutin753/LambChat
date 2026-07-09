import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SidebarSkeleton.tsx", import.meta.url),
  "utf8",
);

test("sidebar skeleton shares repeated rail and nav row primitives", () => {
  expect(source).toMatch(/function SidebarRailIconSkeleton\(\)/);
  expect(source).toMatch(/function SidebarNavRowSkeleton\(/);
  expect(source).toMatch(/className="skeleton-line size-9 rounded-full mx-2"/);
  expect(source).toMatch(
    /className="w-full h-8 rounded-\[10px\] flex items-center gap-3 px-\[9px\]"/,
  );
  expect(source).toMatch(
    /className="skeleton-line size-5 rounded-md shrink-0"/,
  );

  expect(source.match(/skeleton-line size-9 rounded-full mx-2/g)?.length).toBe(
    1,
  );
  expect(
    source.match(
      /w-full h-8 rounded-\[10px\] flex items-center gap-3 px-\[9px\]/g,
    )?.length,
  ).toBe(1);
  expect(
    source.match(/skeleton-line size-5 rounded-md shrink-0/g)?.length,
  ).toBe(1);
});
