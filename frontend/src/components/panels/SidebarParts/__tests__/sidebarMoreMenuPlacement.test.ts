import { readFileSync } from "node:fs";
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

  expect(coreMoreMenuMatch).toBeTruthy();
  expect(coreMoreMenuMatch[0]).toMatch(/path:\s*"\/persona"/);
  expect(coreMoreMenuMatch[0]).not.toMatch(/path:\s*"\/team"/);
  expect(coreContributionsSource).not.toMatch(/BUILTIN_PLUGIN_SIDEBAR_MORE_NAV/);
  expect(coreMoreMenuMatch[0]).not.toMatch(/href:\s*GITHUB_URL/);
  expect(coreMoreMenuMatch[0]).not.toMatch(/label:\s*t\("nav\.contribute"/);
  expect(useMoreMenuSource).toMatch(/buildSidebarMoreNavContributions\(runtimePlugins\)/);
  expect(coreContributionsSource).toMatch(/plugin\.frontend\?\.sidebar_items/);
});

test("persona and team are not rendered as primary sidebar actions", () => {
  expect(sessionListContentSource).not.toMatch(/navigate\("\/persona"\)/);
  expect(sessionListContentSource).not.toMatch(/navigate\("\/team"\)/);
  expect(sidebarRailSource).not.toMatch(/onOpenPersonaPlaza/);
  expect(sidebarRailSource).not.toMatch(/onOpenTeamBuilder/);
});

test("sidebar more menu receives plugin contributions on chat and non-chat tabs", () => {
  expect(chatAppContentSource).toMatch(/<SessionSidebar[\s\S]*runtimePlugins=\{runtimePlugins\}/);
  expect(nonChatAppContentSource).toMatch(/<SessionSidebar[\s\S]*runtimePlugins=\{runtimePlugins\}/);
  expect(useMoreMenuSource).toMatch(/buildSidebarMoreNavContributions\(runtimePlugins\)/);
});
