import { readFileSync } from "node:fs";
const welcomePageSource = readFileSync(
  new URL("../WelcomePage.tsx", import.meta.url),
  "utf8",
);
const welcomeSurfaceRendererSource = readFileSync(
  new URL("../welcomeSurfaceRenderers.tsx", import.meta.url),
  "utf8",
);
const chatViewSource = readFileSync(
  new URL("../../layout/AppContent/ChatView.tsx", import.meta.url),
  "utf8",
);

test("welcome page delegates team plaza to plugin welcome surfaces", () => {
  expect(welcomePageSource).toMatch(/currentAgent\?: string;/);
  expect(welcomePageSource).toMatch(/selectedTeamId\?: string \| null;/);
  expect(welcomePageSource).not.toMatch(/onSelectTeam\?:/);
  expect(welcomePageSource).toMatch(/buildWelcomeSurfaceContributions\(chatInputProps\.runtimePlugins/);
  expect(welcomePageSource).toMatch(/<WelcomeSurfaceRenderer/);
  expect(welcomePageSource).not.toMatch(/teamApi\s*\.\s*list/);
  expect(welcomePageSource).not.toMatch(/TeamAvatar/);
  expect(welcomePageSource).not.toMatch(/plugin_id === "agent_team"/);

  expect(welcomeSurfaceRendererSource).toMatch(/teamApi\s*\.\s*list\(0,\s*50\)/);
  expect(welcomeSurfaceRendererSource).toMatch(/"agent_team\.TeamWelcomeSurface"/);
  expect(welcomeSurfaceRendererSource).toMatch(/onClick=\{\(\) => navigate\("\/agent-team"\)\}/);
  expect(welcomeSurfaceRendererSource).toMatch(/onClick=\{\(\) => handleTeamClick\(team\)\}/);
  expect(welcomeSurfaceRendererSource).toMatch(/getWelcomeTeamCards\(teamCards,\s*selectedTeamId\)/);
  expect(chatViewSource).not.toMatch(/selectedAgentTeamIdFromMetadata/);
  expect(chatViewSource).not.toMatch(/selectedPluginTeamId/);
  expect(chatViewSource).toMatch(/selectedTeamId=\{selectedTeamId\}/);
  expect(chatViewSource).not.toMatch(/<WelcomePage[\s\S]*onSelectTeam=\{onSelectTeam\}/);
  expect(chatViewSource).toMatch(/chatInputProps=\{chatInputProps\}/);
});

test("welcome page projects @ mentions through the active welcome surface", () => {
  expect(welcomePageSource).toMatch(/const isAgentReady = !!currentAgent;/);
  expect(welcomePageSource).toMatch(/hasWelcomeSurface \? !selectedTeamId : !selectedPersonaPresetId/);
  expect(welcomePageSource).toMatch(
    /onMentionQueryChange=\{\s*shouldProjectMentionsToWelcome\s*\?\s*handleMentionQueryChange\s*:\s*undefined\s*\}/,
  );
});

test("welcome page keeps persona actions core-owned and delegates team actions", () => {
  expect(welcomePageSource).toMatch(/const canChangePersona =\s*isAgentReady &&\s*!hasWelcomeSurface &&\s*!!selectedPersonaPresetId &&\s*!!onClearPersonaPreset;/);
  expect(welcomePageSource).toMatch(/\(showGallerySection \|\| showStarterPrompts \|\| canChangePersona\)/);
  expect(welcomeSurfaceRendererSource).toMatch(/const canChangeTeam = !!selectedTeamId && !!onPluginOptionChange && !!optionBinding;/);
  expect(welcomePageSource).toMatch(/onPluginOptionChange=\{chatInputProps\.onPluginOptionChange\}/);
  expect(welcomeSurfaceRendererSource).toMatch(/optionBinding\.pluginId,\s*optionBinding\.key,\s*null/);
  expect(welcomeSurfaceRendererSource).not.toMatch(/onSelectTeam\?\.\(null\)/);
  expect(welcomeSurfaceRendererSource).toMatch(/optionBinding\.pluginId,\s*optionBinding\.key,\s*team\.id/);
  expect(welcomeSurfaceRendererSource).not.toMatch(/AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  expect(welcomeSurfaceRendererSource).not.toMatch(/onSelectTeam\?\.\(team\.id\)/);
  expect(welcomeSurfaceRendererSource).toMatch(/t\("team\.change"/);
});

test("welcome team surface uses the same skeleton count as role choices", () => {
  expect(welcomeSurfaceRendererSource).toMatch(/const teamSkeletonCount = getWelcomePersonaSkeletonCount\(\s*shouldShowTeamSkeletons,\s*displayTeamCards\.length,\s*\);/);
  expect(welcomeSurfaceRendererSource).not.toMatch(/getWelcomePersonaSkeletonCount\(\s*shouldShowTeamSkeletons,\s*displayTeamCards\.length,\s*6,\s*\)/);
});

test("welcome team surface renders skeleton cards while teams are loading", () => {
  expect(welcomePageSource).toMatch(/const personaSkeletonCount = getWelcomePersonaSkeletonCount\(\s*personaPresetsLoading,\s*displayCards\.length,\s*\);/);
  expect(welcomeSurfaceRendererSource).toMatch(/\{showTeamCards &&\s*Array\.from\(\{ length: teamSkeletonCount \}\)/);
  expect(welcomeSurfaceRendererSource).toMatch(/className=\{getWelcomePersonaSkeletonClass\(\)\}/);
});

test("welcome team surface treats the first unresolved team request as loading", () => {
  expect(welcomeSurfaceRendererSource).toMatch(/const \[teamCardsLoaded, setTeamCardsLoaded\] = useState\(false\);/);
  expect(welcomeSurfaceRendererSource).toMatch(/setTeamCardsLoaded\(false\);/);
  expect(welcomeSurfaceRendererSource).toMatch(/setTeamCardsLoaded\(true\);/);
  expect(welcomeSurfaceRendererSource).toMatch(/const shouldShowTeamSkeletons =\s*showTeamCards && \(teamCardsLoading \|\| !teamCardsLoaded\);/);
});

test("welcome page does not treat an unresolved agent as persona mode", () => {
  expect(welcomePageSource).toMatch(/const showPersonaCards =\s*isAgentReady && !hasWelcomeSurface &&/);
  expect(welcomePageSource).toMatch(/const showStarterPrompts =\s*isAgentReady &&\s*!hasWelcomeSurface &&/);
});
