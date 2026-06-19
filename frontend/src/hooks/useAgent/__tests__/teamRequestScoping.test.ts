import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../../useAgent.ts", import.meta.url),
  "utf8",
);
const typesSource = readFileSync(
  new URL("../types.ts", import.meta.url),
  "utf8",
);

test("submits session plugin options from active plugin declarations", () => {
  assert.match(source, /const isCurrentAgentAvailable = useCallback/);
  assert.match(source, /agents\.some\(\(agent\) => agent\.id === agentId\)/);
  assert.match(source, /const currentSessionOptionContributions = useMemo/);
  assert.match(source, /buildSessionOptionContributions\(options\?\.runtimePlugins/);
  assert.match(
    source,
    /retainPluginOptionsForDeclarations\([\s\S]*sessionOptionSeed,[\s\S]*currentSessionOptionContributions[\s\S]*\)/,
  );
  assert.match(source, /importLegacyPayloadPluginOptions/);
  assert.match(source, /legacyPayloadKeysForPluginOption/);
  assert.doesNotMatch(source, /isCurrentAgentAvailable\(AGENT_TEAM_LEGACY_AGENT_ID\)/);
  assert.doesNotMatch(source, /currentAgent === AGENT_TEAM_LEGACY_AGENT_ID/);
  assert.doesNotMatch(source, /canUseCurrentTeamAgent/);
  assert.match(
    source,
    /const canUseLegacyTeamField =[\s\S]*selectedTeamId[\s\S]*isCurrentAgentAvailable\(currentAgent\)[\s\S]*hasAgentCatalogEntryContribution\(currentAgent, options\?\.runtimePlugins\)/,
  );
  assert.match(
    source,
    /const requestTeamId = canUseLegacyTeamField && Object\.keys\(requestPluginOptions\)\.length === 0[\s\S]*\?[\s\S]*selectedTeamId[\s\S]*:[\s\S]*null/,
  );
  assert.match(
    source,
    /const sessionOptionSeed = importLegacyPayloadPluginOptions\([\s\S]*plugin_options: sessionPluginOptions,[\s\S]*team_id: legacyTeamId \?\? undefined,[\s\S]*currentSessionOptionContributions,[\s\S]*sessionPluginOptions[\s\S]*\)/,
  );
  assert.doesNotMatch(source, /withSelectedAgentTeamId/);
  assert.match(
    source,
    /requestTeamId,[\s\S]*requestPluginOptions,[\s\S]*goalForRun/,
  );
});

test("stores Agent Team optimistic session metadata only under plugin options", () => {
  assert.doesNotMatch(source, /conversationConfig\.team_id\s*=\s*selectedTeamId/);
  assert.doesNotMatch(source, /conversationConfig\.team_id\s*=\s*requestTeamId/);
  assert.match(source, /conversationConfig\.plugin_options = requestPluginOptions/);
  assert.match(source, /isCurrentAgentAvailable,/);
  assert.match(source, /hasAgentCatalogEntryContribution/);
  assert.match(source, /currentSessionOptionContributions,/);
});

test("keeps Team selection writes in the plugin namespace rather than optimistic legacy metadata", () => {
  assert.match(source, /const \[legacyTeamId, setLegacyTeamId\]/);
  assert.match(
    source,
    /const selectedTeamId = selectedAgentTeamIdFromMetadata\([\s\S]*plugin_options: sessionPluginOptions,[\s\S]*team_id: legacyTeamId \?\? undefined/,
  );
  assert.match(source, /const \[sessionPluginOptions, setSessionPluginOptions\]/);
  assert.match(source, /const setSessionPluginOption = useCallback/);
  assert.match(source, /setSessionPluginOptions\(\(current\) =>/);
  assert.match(source, /withPluginOption\([\s\S]*pluginId,[\s\S]*key,[\s\S]*value/);
  assert.match(
    source,
    /legacyPayloadKeysForPluginOption\(option\)\.includes\("team_id"\)/,
  );
  assert.doesNotMatch(source, /isAgentTeamSelectedTeamOption\(pluginId, key\)/);
  assert.match(source, /setLegacyTeamId\(null\)/);
  assert.doesNotMatch(source, /selectTeam = useCallback/);
  assert.doesNotMatch(typesSource, /selectTeam:/);
  assert.match(source, /requestPluginOptions/);
  assert.match(source, /plugin_options: requestPluginOptions|conversationConfig\.plugin_options = requestPluginOptions/);
  assert.doesNotMatch(source, /team_id:\s*requestTeamId/);
  assert.doesNotMatch(source, /metadata:\s*{[\s\S]*team_id:\s*selectedTeamId/);
  assert.doesNotMatch(source, /submitChat\([\s\S]*team_id:\s*selectedTeamId/);
});
