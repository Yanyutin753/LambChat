import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const chatInputSource = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);
const mentionProviderRenderersSource = readFileSync(
  new URL("../chatMentionProviderRenderers.tsx", import.meta.url),
  "utf8",
);

test("team agent mention switches teams instead of persona presets", () => {
  assert.doesNotMatch(chatInputSource, /useTeamMentionSearch/);
  assert.doesNotMatch(chatInputSource, /TeamMentionPopup/);
  assert.match(chatInputSource, /buildMentionProviderContributions/);
  assert.match(chatInputSource, /isPluginMentionProviderSupported/);
  assert.match(chatInputSource, /usePluginMentionProviderRuntime/);
  assert.match(chatInputSource, /const mentionMode = activePluginMentionProvider\?\.mode \?\? "persona"/);
  assert.doesNotMatch(chatInputSource, /currentAgent === "team"[\s\S]*\? "team"[\s\S]*: "persona"/);
  assert.doesNotMatch(chatInputSource, /applyTeamMentionSelection/);
  assert.match(mentionProviderRenderersSource, /useTeamMentionSearch/);
  assert.match(mentionProviderRenderersSource, /provider\.provider === "agent_team\.searchTeams"/);
  assert.match(mentionProviderRenderersSource, /provider\.optionBinding/);
  assert.match(mentionProviderRenderersSource, /optionBinding\.pluginId,\s*optionBinding\.key,\s*team\.id/);
  assert.doesNotMatch(mentionProviderRenderersSource, /AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  assert.doesNotMatch(mentionProviderRenderersSource, /onSelectTeam/);
  assert.doesNotMatch(chatInputSource, /isPluginMentionProviderSupported\(provider, \{[\s\S]*onSelectTeam/);
  assert.match(chatInputSource, /onPluginOptionChange: handlePluginOptionChange/);
  assert.match(mentionProviderRenderersSource, /<TeamMentionPopup/);
  assert.match(mentionProviderRenderersSource, /mode: provider\.mode/);
  assert.match(chatInputSource, /mentionMode === "persona"/);
});

test("team agent placeholder says @ switches teams", () => {
  assert.match(mentionProviderRenderersSource, /chat\.teamPlaceholder/);
  assert.match(
    chatInputSource,
    /pluginMentionRuntime\?\.placeholderKey[\s\S]*t\(pluginMentionRuntime\.placeholderKey\)/,
  );
});

test("team agent can submit without selecting an existing team", () => {
  assert.doesNotMatch(chatInputSource, /requiresTeamSelection/);
  assert.doesNotMatch(chatInputSource, /!\s*requiresTeamSelection/);
});
