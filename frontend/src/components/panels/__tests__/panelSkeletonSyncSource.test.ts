import { readFileSync } from "node:fs";
import { join } from "node:path";

const skillsListSource = readFileSync(
  join(import.meta.dirname, "../SkillsPanel/SkillsList.tsx"),
  "utf8",
);

const memoryPanelSource = readFileSync(
  join(import.meta.dirname, "../MemoryPanel/index.tsx"),
  "utf8",
);

const skeletonIndexSource = readFileSync(
  join(import.meta.dirname, "../../skeletons/index.ts"),
  "utf8",
);

test("embedded skills list loading uses an embedded skeleton", () => {
  expect(skillsListSource).toMatch(/SkillsListSkeleton/);
  expect(skillsListSource).toMatch(
    /return embedded \? <SkillsListSkeleton \/> : <SkillsPanelSkeleton \/>/,
  );
});

test("memory panel initial loading uses a panel-specific skeleton", () => {
  expect(memoryPanelSource).toMatch(/import \{ MemoryPanelSkeleton \}/);
  expect(memoryPanelSource).toMatch(/<MemoryPanelSkeleton \/>/);
  expect(memoryPanelSource).not.toMatch(/<PanelLoadingState \/>/);
  expect(skeletonIndexSource).toMatch(/MemoryPanelSkeleton/);
});
