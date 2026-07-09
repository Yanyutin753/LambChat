import { readFileSync } from "node:fs";
const helpersSource = readFileSync(
  new URL("../PanelSkeletonHelpers.tsx", import.meta.url),
  "utf8",
);
const skillSkeletonSource = readFileSync(
  new URL("../SkillSkeletons.tsx", import.meta.url),
  "utf8",
);
const channelSkeletonSource = readFileSync(
  new URL("../ChannelSkeletons.tsx", import.meta.url),
  "utf8",
);
const adminSkeletonSource = readFileSync(
  new URL("../AdminSkeletons.tsx", import.meta.url),
  "utf8",
);
const infraSkeletonSource = readFileSync(
  new URL("../InfraSkeletons.tsx", import.meta.url),
  "utf8",
);

test("card grid panel skeletons render twenty-four placeholder cards", () => {
  expect(helpersSource).toMatch(/export const PANEL_CARD_SKELETON_COUNT = 24;/);

  for (const source of [
    skillSkeletonSource,
    channelSkeletonSource,
    adminSkeletonSource,
    infraSkeletonSource,
  ]) {
    expect(source).toMatch(/PANEL_CARD_SKELETON_COUNT/);
    expect(source).not.toMatch(/length:\s*12/);
    expect(source).not.toMatch(/count\s*=\s*12/);
  }
});
