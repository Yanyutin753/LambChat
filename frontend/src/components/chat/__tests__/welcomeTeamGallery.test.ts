import { readFileSync } from "node:fs";
const welcomePageSource = readFileSync(
  new URL("../WelcomePage.tsx", import.meta.url),
  "utf8",
);
const chatSkeletonsSource = readFileSync(
  new URL("../../skeletons/ChatSkeletons.tsx", import.meta.url),
  "utf8",
);
const chatViewSource = readFileSync(
  new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
  "utf8",
);

test("welcome page switches the plaza to teams when team agent is active", () => {
  expect(welcomePageSource).toMatch(/currentAgent\?: string;/);
  expect(welcomePageSource).toMatch(/selectedTeamId\?: string \| null;/);
  expect(welcomePageSource).toMatch(
    /onSelectTeam\?: \(teamId: string \| null\) => void;/,
  );
  expect(welcomePageSource).toMatch(/teamApi\s*\.\s*list\(0,\s*50\)/);
  expect(welcomePageSource).toMatch(
    /const showTeamCards =[\s\S]*currentAgent === "team"/,
  );
  expect(welcomePageSource).toMatch(/onClick=\{\(\) => navigate\("\/team"\)\}/);
  expect(welcomePageSource).toMatch(
    /onClick=\{\(\) => handleTeamClick\(team\)\}/,
  );
  expect(welcomePageSource).toMatch(
    /getWelcomeTeamCards\(teamCards,\s*selectedTeamId\)/,
  );
  expect(chatViewSource).toMatch(
    /currentAgent=\{currentAgent\}[\s\S]*selectedTeamId=\{selectedTeamId\}[\s\S]*onSelectTeam=\{onSelectTeam\}/,
  );
});

test("welcome page only projects @ mentions to welcome cards before a role or team is selected", () => {
  expect(welcomePageSource).toMatch(/const isAgentReady = !!currentAgent;/);
  expect(welcomePageSource).toMatch(
    /const shouldProjectMentionsToWelcome =\s*isAgentReady &&\s*\(currentAgent === "team"\s*\?\s*!selectedTeamId\s*:\s*!selectedPersonaPresetId\);/,
  );
  expect(welcomePageSource).toMatch(
    /onMentionQueryChange=\{\s*shouldProjectMentionsToWelcome\s*\?\s*handleMentionQueryChange\s*:\s*undefined\s*\}/,
  );
});

test("welcome page keeps change role and change team actions visible after selection", () => {
  expect(welcomePageSource).toMatch(
    /const canChangePersona =\s*isAgentReady &&\s*currentAgent !== "team" &&\s*!!selectedPersonaPresetId &&\s*!!onClearPersonaPreset;/,
  );
  expect(welcomePageSource).toMatch(
    /const canChangeTeam =\s*currentAgent === "team" && !!selectedTeamId && !!onSelectTeam;/,
  );
  expect(welcomePageSource).toMatch(
    /const showSelectionActions = canChangePersona \|\| canChangeTeam;/,
  );
  expect(welcomePageSource).toMatch(
    /\(showGallerySection\s*\|\|\s*showStarterPrompts\s*\|\|\s*showTeamStarterPrompts\s*\|\|\s*showSelectionActions\)/,
  );
  expect(welcomePageSource).toMatch(/onSelectTeam\?\.\(null\)/);
  expect(welcomePageSource).toMatch(/t\("team\.change", "更换团队"\)/);
});

test("welcome page uses the same skeleton count for role and team choices", () => {
  expect(welcomePageSource).toMatch(
    /const teamSkeletonCount = getWelcomePersonaSkeletonCount\(\s*shouldShowTeamSkeletons,\s*displayTeamCards\.length,\s*\);/,
  );
  expect(welcomePageSource).not.toMatch(
    /getWelcomePersonaSkeletonCount\(\s*shouldShowTeamSkeletons,\s*displayTeamCards\.length,\s*6,\s*\)/,
  );
});

test("welcome team plaza renders skeleton cards while teams are loading", () => {
  expect(welcomePageSource).toMatch(
    /const personaSkeletonCount = getWelcomePersonaSkeletonCount\(\s*personaPresetsLoading,\s*displayCards\.length,\s*\);/,
  );
  expect(welcomePageSource).toMatch(
    /\{showTeamCards &&\s*Array\.from\(\{ length: teamSkeletonCount \}\)/,
  );
  expect(chatSkeletonsSource).toMatch(
    /className=\{getWelcomePersonaSkeletonClass\(\)\}/,
  );
});

test("welcome team plaza treats the first unresolved team request as loading", () => {
  expect(welcomePageSource).toMatch(
    /const \[teamRequestState, setTeamRequestState\] = useState</,
  );
  expect(welcomePageSource).toMatch(
    /teamCardsLoaded = teamRequestState\.isSettled;/,
  );
  expect(welcomePageSource).toMatch(
    /const shouldShowTeamSkeletons =\s*showTeamCards && \(teamCardsLoading \|\| !teamCardsLoaded\);/,
  );
});

test("welcome page invalidates team cards before paint and gates content on readiness", () => {
  expect(welcomePageSource).toMatch(
    /import \{[^}]*useLayoutEffect[^}]*\} from "react";/,
  );
  expect(welcomePageSource).toMatch(/useLayoutEffect\([\s\S]*beginTeamRequest/);
  expect(welcomePageSource).toMatch(/isWelcomeContentReady\(/);
  // 骨架只覆盖首次加载（issue #158）：一旦内容就绪过，背景 refetch
  // 不得把欢迎页重新落回骨架（否则弹窗状态随整页卸载丢失）。
  expect(welcomePageSource).toMatch(/hasEverBeenReadyRef\.current = true;/);
  expect(welcomePageSource).toMatch(
    /shouldRenderWelcomeSkeleton\(\s*welcomeContentReady,\s*hasEverBeenReadyRef\.current,\s*\)/,
  );
  expect(welcomePageSource).toMatch(/return <WelcomeSkeleton \/>;/);
});

test("welcome page does not treat an unresolved agent as persona mode", () => {
  expect(welcomePageSource).toMatch(
    /const showPersonaCards =\s*isAgentReady &&\s*currentAgent !== "team" &&/,
  );
  expect(welcomePageSource).toMatch(
    /const showStarterPrompts =\s*isAgentReady &&\s*currentAgent !== "team" &&/,
  );
});
