import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

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
  assert.match(welcomePageSource, /currentAgent\?: string;/);
  assert.match(welcomePageSource, /selectedTeamId\?: string \| null;/);
  assert.doesNotMatch(welcomePageSource, /onSelectTeam\?:/);
  assert.match(
    welcomePageSource,
    /buildWelcomeSurfaceContributions\(chatInputProps\.runtimePlugins/,
  );
  assert.match(welcomePageSource, /<WelcomeSurfaceRenderer/);
  assert.doesNotMatch(welcomePageSource, /teamApi\s*\.\s*list/);
  assert.doesNotMatch(welcomePageSource, /TeamAvatar/);
  assert.doesNotMatch(welcomePageSource, /plugin_id === "agent_team"/);

  assert.match(welcomeSurfaceRendererSource, /teamApi\s*\.\s*list\(0,\s*50\)/);
  assert.match(welcomeSurfaceRendererSource, /"agent_team\.TeamWelcomeSurface"/);
  assert.match(welcomeSurfaceRendererSource, /onClick=\{\(\) => navigate\("\/team"\)\}/);
  assert.match(
    welcomeSurfaceRendererSource,
    /onClick=\{\(\) => handleTeamClick\(team\)\}/,
  );
  assert.match(
    welcomeSurfaceRendererSource,
    /getWelcomeTeamCards\(teamCards,\s*selectedTeamId\)/,
  );
  assert.doesNotMatch(chatViewSource, /selectedAgentTeamIdFromMetadata/);
  assert.doesNotMatch(chatViewSource, /selectedPluginTeamId/);
  assert.match(chatViewSource, /selectedTeamId=\{selectedTeamId\}/);
  assert.doesNotMatch(chatViewSource, /<WelcomePage[\s\S]*onSelectTeam=\{onSelectTeam\}/);
  assert.match(chatViewSource, /chatInputProps=\{chatInputProps\}/);
});

test("welcome page projects @ mentions through the active welcome surface", () => {
  assert.match(welcomePageSource, /const isAgentReady = !!currentAgent;/);
  assert.match(
    welcomePageSource,
    /hasWelcomeSurface \? !selectedTeamId : !selectedPersonaPresetId/,
  );
  assert.match(
    welcomePageSource,
    /onMentionQueryChange=\{\s*shouldProjectMentionsToWelcome\s*\?\s*handleMentionQueryChange\s*:\s*undefined\s*\}/,
  );
});

test("welcome page keeps persona actions core-owned and delegates team actions", () => {
  assert.match(
    welcomePageSource,
    /const canChangePersona =\s*isAgentReady &&\s*!hasWelcomeSurface &&\s*!!selectedPersonaPresetId &&\s*!!onClearPersonaPreset;/,
  );
  assert.match(
    welcomePageSource,
    /\(showGallerySection \|\| showStarterPrompts \|\| canChangePersona\)/,
  );
  assert.match(
    welcomeSurfaceRendererSource,
    /const canChangeTeam = !!selectedTeamId && !!onPluginOptionChange && !!optionBinding;/,
  );
  assert.match(welcomePageSource, /onPluginOptionChange=\{chatInputProps\.onPluginOptionChange\}/);
  assert.match(welcomeSurfaceRendererSource, /optionBinding\.pluginId,\s*optionBinding\.key,\s*null/);
  assert.doesNotMatch(welcomeSurfaceRendererSource, /onSelectTeam\?\.\(null\)/);
  assert.match(welcomeSurfaceRendererSource, /optionBinding\.pluginId,\s*optionBinding\.key,\s*team\.id/);
  assert.doesNotMatch(welcomeSurfaceRendererSource, /AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  assert.doesNotMatch(welcomeSurfaceRendererSource, /onSelectTeam\?\.\(team\.id\)/);
  assert.match(welcomeSurfaceRendererSource, /t\("team\.change"/);
});

test("welcome team surface uses the same skeleton count as role choices", () => {
  assert.match(
    welcomeSurfaceRendererSource,
    /const teamSkeletonCount = getWelcomePersonaSkeletonCount\(\s*shouldShowTeamSkeletons,\s*displayTeamCards\.length,\s*\);/,
  );
  assert.doesNotMatch(
    welcomeSurfaceRendererSource,
    /getWelcomePersonaSkeletonCount\(\s*shouldShowTeamSkeletons,\s*displayTeamCards\.length,\s*6,\s*\)/,
  );
});

test("welcome team surface renders skeleton cards while teams are loading", () => {
  assert.match(
    welcomePageSource,
    /const personaSkeletonCount = getWelcomePersonaSkeletonCount\(\s*personaPresetsLoading,\s*displayCards\.length,\s*\);/,
  );
  assert.match(
    welcomeSurfaceRendererSource,
    /\{showTeamCards &&\s*Array\.from\(\{ length: teamSkeletonCount \}\)/,
  );
  assert.match(welcomeSurfaceRendererSource, /className=\{getWelcomePersonaSkeletonClass\(\)\}/);
});

test("welcome team surface treats the first unresolved team request as loading", () => {
  assert.match(
    welcomeSurfaceRendererSource,
    /const \[teamCardsLoaded, setTeamCardsLoaded\] = useState\(false\);/,
  );
  assert.match(welcomeSurfaceRendererSource, /setTeamCardsLoaded\(false\);/);
  assert.match(welcomeSurfaceRendererSource, /setTeamCardsLoaded\(true\);/);
  assert.match(
    welcomeSurfaceRendererSource,
    /const shouldShowTeamSkeletons =\s*showTeamCards && \(teamCardsLoading \|\| !teamCardsLoaded\);/,
  );
});

test("welcome page does not treat an unresolved agent as persona mode", () => {
  assert.match(
    welcomePageSource,
    /const showPersonaCards =\s*isAgentReady && !hasWelcomeSurface &&/,
  );
  assert.match(
    welcomePageSource,
    /const showStarterPrompts =\s*isAgentReady &&\s*!hasWelcomeSurface &&/,
  );
});
