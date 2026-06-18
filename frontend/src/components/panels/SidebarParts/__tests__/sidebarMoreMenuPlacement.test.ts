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
const chatAppContentSource = readFileSync(
  new URL("../../../layout/AppContent/ChatAppContent.tsx", import.meta.url),
  "utf8",
);
const nonChatAppContentSource = readFileSync(
  new URL("../../../layout/AppContent/NonChatAppContent.tsx", import.meta.url),
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
  expect(sessionListContentSource).not.toMatch(/navigate\("\/persona"\)/);
  expect(sessionListContentSource).not.toMatch(/navigate\("\/team"\)/);
  expect(sidebarRailSource).not.toMatch(/onOpenPersonaPlaza/);
  expect(sidebarRailSource).not.toMatch(/onOpenTeamBuilder/);
});

test("sidebar more menu receives plugin contributions on chat and non-chat tabs", () => {
  assert.match(chatAppContentSource, /<SessionSidebar[\s\S]*runtimePlugins=\{runtimePlugins\}/);
  assert.match(nonChatAppContentSource, /<SessionSidebar[\s\S]*runtimePlugins=\{runtimePlugins\}/);
  assert.match(useMoreMenuSource, /buildSidebarMoreNavContributions\(runtimePlugins\)/);
});
