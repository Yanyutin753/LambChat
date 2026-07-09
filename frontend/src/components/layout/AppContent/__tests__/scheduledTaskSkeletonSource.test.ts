import { readFileSync } from "node:fs";
function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("scheduled task route uses a matching panel skeleton while lazy loading", () => {
  const tabContent = readSource("../TabContent.tsx");
  const panelSkeletons = readSource("../../../skeletons/PanelSkeletons.tsx");
  const infraSkeletons = readSource("../../../skeletons/InfraSkeletons.tsx");
  const skeletonIndex = readSource("../../../skeletons/index.ts");

  expect(infraSkeletons).toMatch(/export function ScheduledTaskPanelSkeleton/);
  expect(panelSkeletons).toMatch(/ScheduledTaskPanelSkeleton/);
  expect(skeletonIndex).toMatch(/ScheduledTaskPanelSkeleton/);
  expect(tabContent).toMatch(
    /import \{[\s\S]*ScheduledTaskPanelSkeleton[\s\S]*\} from "\.\.\/\.\.\/skeletons"/,
  );
  expect(tabContent).toMatch(
    /"scheduled-tasks":\s*<ScheduledTaskPanelSkeleton \/>/,
  );
  expect(tabContent).toMatch(
    /fallback=\{skeletonMap\[activeTab\] \?\? <PanelLoadingState \/>/,
  );
});
