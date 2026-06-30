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
const chatAppContentSource = readFileSync(
  new URL("../../../layout/AppContent/ChatAppContent.tsx", import.meta.url),
  "utf8",
);
const nonChatAppContentSource = readFileSync(
  new URL("../../../layout/AppContent/NonChatAppContent.tsx", import.meta.url),
  "utf8",
);

test("persona lives in the core more menu while team is plugin-owned", () => {
  const coreMoreMenuMatch = coreContributionsSource.match(
    /CORE_SIDEBAR_MORE_NAV[\s\S]*?\];/,
  );

  assert.ok(coreMoreMenuMatch, "core more menu item config should exist");
  assert.match(coreMoreMenuMatch[0], /path:\s*"\/persona"/);
  assert.doesNotMatch(coreMoreMenuMatch[0], /path:\s*"\/team"/);
  assert.doesNotMatch(coreContributionsSource, /BUILTIN_PLUGIN_SIDEBAR_MORE_NAV/);
  assert.doesNotMatch(coreMoreMenuMatch[0], /href:\s*GITHUB_URL/);
  assert.doesNotMatch(coreMoreMenuMatch[0], /label:\s*t\("nav\.contribute"/);
  assert.match(useMoreMenuSource, /buildSidebarMoreNavContributions\(runtimePlugins\)/);
  assert.match(coreContributionsSource, /plugin\.frontend\?\.sidebar_items/);
});

test("persona and team are not rendered as primary sidebar actions", () => {
  assert.doesNotMatch(sessionListContentSource, /navigate\("\/persona"\)/);
  assert.doesNotMatch(sessionListContentSource, /navigate\("\/team"\)/);
  assert.doesNotMatch(sidebarRailSource, /onOpenPersonaPlaza/);
  assert.doesNotMatch(sidebarRailSource, /onOpenTeamBuilder/);
});

test("sidebar more menu receives plugin contributions on chat and non-chat tabs", () => {
  assert.match(chatAppContentSource, /<SessionSidebar[\s\S]*runtimePlugins=\{runtimePlugins\}/);
  assert.match(nonChatAppContentSource, /<SessionSidebar[\s\S]*runtimePlugins=\{runtimePlugins\}/);
  assert.match(useMoreMenuSource, /buildSidebarMoreNavContributions\(runtimePlugins\)/);
});
