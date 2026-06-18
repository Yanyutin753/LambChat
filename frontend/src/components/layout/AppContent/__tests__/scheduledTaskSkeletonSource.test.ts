import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

test("scheduled task route uses a matching panel skeleton while lazy loading", () => {
  const tabContent = readSource("../TabContent.tsx");
  const panelSkeletons = readSource("../../../skeletons/PanelSkeletons.tsx");
  const infraSkeletons = readSource("../../../skeletons/InfraSkeletons.tsx");
  const skeletonIndex = readSource("../../../skeletons/index.ts");

  assert.match(infraSkeletons, /export function ScheduledTaskPanelSkeleton/);
  assert.match(panelSkeletons, /ScheduledTaskPanelSkeleton/);
  assert.match(skeletonIndex, /ScheduledTaskPanelSkeleton/);
  assert.match(
    tabContent,
    /import \{[\s\S]*ScheduledTaskPanelSkeleton[\s\S]*\} from "\.\.\/\.\.\/skeletons"/,
  );
  assert.match(
    tabContent,
    /"scheduled-tasks":\s*<ScheduledTaskPanelSkeleton \/>/,
  );
  assert.match(
    tabContent,
    /fallback=\{skeletonMap\[activeTab\] \?\? <PanelLoadingState \/>/,
  );
});
