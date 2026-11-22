import { readFileSync } from "node:fs";
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
  const moreMenuMatch = useMoreMenuSource.match(
    /const moreMenuFeatureItems = \[[\s\S]*?\];/,
  );

  expect(moreMenuMatch).toBeTruthy();
  expect(moreMenuMatch[0]).toMatch(/path:\s*"\/persona"/);
  expect(moreMenuMatch[0]).toMatch(/path:\s*"\/team"/);
  expect(moreMenuMatch[0]).not.toMatch(/href:\s*GITHUB_URL/);
  expect(moreMenuMatch[0]).not.toMatch(/label:\s*t\("nav\.contribute"/);
});

test("persona and team are not rendered as primary sidebar actions", () => {
  expect(sessionListContentSource).not.toMatch(/navigate\("\/persona"\)/);
  expect(sessionListContentSource).not.toMatch(/navigate\("\/team"\)/);
  expect(sidebarRailSource).not.toMatch(/onOpenPersonaPlaza/);
  expect(sidebarRailSource).not.toMatch(/onOpenTeamBuilder/);
});

test("expanded desktop sidebar exposes labeled feature navigation", () => {
  expect(sessionListContentSource).not.toContain(
    "!compactChrome && hasMoreMenuItems",
  );
  expect(sessionListContentSource).not.toContain(
    "!compactChrome && canReadScheduledTasks",
  );
});

test("the mobile More dialog opens only inside an open mobile drawer", () => {
  const sidebar = readFileSync(
    new URL("../../SessionSidebar.tsx", import.meta.url),
    "utf8",
  );
  expect(sidebar).toMatch(
    /<MobileMoreMenuSheet\b[^>]*isOpen=\{isMobile && mobileOpen && moreMenu\.isMoreMenuOpen\}/,
  );
});
