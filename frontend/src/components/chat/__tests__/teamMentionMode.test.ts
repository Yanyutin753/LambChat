import { readFileSync } from "node:fs";
const chatInputSource = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);
const mentionProviderRenderersSource = readFileSync(
  new URL("../chatMentionProviderRenderers.tsx", import.meta.url),
  "utf8",
);

test("team agent mention switches teams instead of persona presets", () => {
  expect(chatInputSource).not.toMatch(/useTeamMentionSearch/);
  expect(chatInputSource).not.toMatch(/TeamMentionPopup/);
  expect(chatInputSource).toMatch(/buildMentionProviderContributions/);
  expect(chatInputSource).toMatch(/isPluginMentionProviderSupported/);
  expect(chatInputSource).toMatch(/usePluginMentionProviderRuntime/);
  expect(chatInputSource).toMatch(/const mentionMode:[\s\S]*activePluginMentionProvider\?\.mode === "team" \? "team" : "persona"/);
  expect(chatInputSource).not.toMatch(/currentAgent === "team"[\s\S]*\? "team"[\s\S]*: "persona"/);
  expect(chatInputSource).not.toMatch(/applyTeamMentionSelection/);
  expect(mentionProviderRenderersSource).toMatch(/useTeamMentionSearch/);
  expect(mentionProviderRenderersSource).toMatch(/provider\.provider === "agent_team\.searchTeams"/);
  expect(mentionProviderRenderersSource).toMatch(/provider\.optionBinding/);
  expect(mentionProviderRenderersSource).toMatch(/optionBinding\.pluginId,\s*optionBinding\.key,\s*team\.id/);
  expect(mentionProviderRenderersSource).not.toMatch(/AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  expect(mentionProviderRenderersSource).not.toMatch(/onSelectTeam/);
  expect(chatInputSource).not.toMatch(/isPluginMentionProviderSupported\(provider, \{[\s\S]*onSelectTeam/);
  expect(chatInputSource).toMatch(/onPluginOptionChange: handlePluginOptionChange/);
  expect(mentionProviderRenderersSource).toMatch(/<TeamMentionPopup/);
  expect(mentionProviderRenderersSource).toMatch(/mode: provider\.mode/);
  expect(chatInputSource).toMatch(/mentionMode === "persona"/);
});

test("team agent placeholder says @ switches teams", () => {
  expect(mentionProviderRenderersSource).toMatch(/chat\.teamPlaceholder/);
  expect(chatInputSource).toMatch(/pluginMentionRuntime\?\.placeholderKey[\s\S]*t\(pluginMentionRuntime\.placeholderKey\)/);
});

test("team agent can submit without selecting an existing team", () => {
  expect(chatInputSource).not.toMatch(/requiresTeamSelection/);
  expect(chatInputSource).not.toMatch(/!\s*requiresTeamSelection/);
});
