import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const coreContributionsSource = readFileSync(
  new URL("../../../../extensions/coreContributions.ts", import.meta.url),
  "utf8",
);
const useMoreMenuSource = readFileSync(
  new URL("../../../../hooks/useMoreMenu.ts", import.meta.url),
  "utf8",
);
const sessionListContentSource = readFileSync(
  new URL("../SessionListContent.tsx", import.meta.url),
  "utf8",
);
const sidebarRailSource = readFileSync(
  new URL("../SidebarRail.tsx", import.meta.url),
  "utf8",
);

test("persona and team entries live in the more menu", () => {
  const moreMenuMatch = coreContributionsSource.match(
    /CORE_SIDEBAR_MORE_NAV[\s\S]*?\];/,
  );

  assert.ok(moreMenuMatch, "more menu item config should exist");
  assert.match(moreMenuMatch[0], /path:\s*"\/persona"/);
  assert.match(moreMenuMatch[0], /path:\s*"\/team"/);
  assert.doesNotMatch(moreMenuMatch[0], /href:\s*GITHUB_URL/);
  assert.doesNotMatch(moreMenuMatch[0], /label:\s*t\("nav\.contribute"/);
  assert.match(useMoreMenuSource, /CORE_SIDEBAR_MORE_NAV\.map/);
});

test("persona and team are not rendered as primary sidebar actions", () => {
  assert.doesNotMatch(sessionListContentSource, /navigate\("\/persona"\)/);
  assert.doesNotMatch(sessionListContentSource, /navigate\("\/team"\)/);
  assert.doesNotMatch(sidebarRailSource, /onOpenPersonaPlaza/);
  assert.doesNotMatch(sidebarRailSource, /onOpenTeamBuilder/);
});
