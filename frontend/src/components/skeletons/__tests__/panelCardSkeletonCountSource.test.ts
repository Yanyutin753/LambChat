import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

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
  assert.match(helpersSource, /export const PANEL_CARD_SKELETON_COUNT = 24;/);

  for (const source of [
    skillSkeletonSource,
    channelSkeletonSource,
    adminSkeletonSource,
    infraSkeletonSource,
  ]) {
    assert.match(source, /PANEL_CARD_SKELETON_COUNT/);
    assert.doesNotMatch(source, /length:\s*12/);
    assert.doesNotMatch(source, /count\s*=\s*12/);
  }
});
