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
  expect(source).toMatch(/const isCurrentAgentAvailable = useCallback/);
  expect(source).toMatch(/agents\.some\(\(agent\) => agent\.id === agentId\)/);
  expect(source).toMatch(/const currentSessionOptionContributions = useMemo/);
  expect(source).toMatch(/buildSessionOptionContributions\(options\?\.runtimePlugins/);
  expect(source).toMatch(/retainPluginOptionsForDeclarations\([\s\S]*sessionOptionSeed,[\s\S]*currentSessionOptionContributions[\s\S]*\)/);
  expect(source).toMatch(/importLegacyPayloadPluginOptions/);
  expect(source).toMatch(/legacyPayloadKeysForPluginOption/);
  expect(source).not.toMatch(/isCurrentAgentAvailable\(AGENT_TEAM_LEGACY_AGENT_ID\)/);
  expect(source).not.toMatch(/currentAgent === AGENT_TEAM_LEGACY_AGENT_ID/);
  expect(source).not.toMatch(/canUseCurrentTeamAgent/);
  expect(source).toMatch(/const canUseLegacyTeamField =[\s\S]*selectedTeamId[\s\S]*isCurrentAgentAvailable\(currentAgent\)[\s\S]*hasAgentCatalogEntryContribution\(currentAgent, options\?\.runtimePlugins\)/);
  expect(source).toMatch(/const requestTeamId = canUseLegacyTeamField && Object\.keys\(requestPluginOptions\)\.length === 0[\s\S]*\?[\s\S]*selectedTeamId[\s\S]*:[\s\S]*null/);
  expect(source).toMatch(/const sessionOptionSeed = importLegacyPayloadPluginOptions\([\s\S]*plugin_options: sessionPluginOptions,[\s\S]*team_id: legacyTeamId \?\? undefined,[\s\S]*currentSessionOptionContributions,[\s\S]*sessionPluginOptions[\s\S]*\)/);
  expect(source).not.toMatch(/withSelectedAgentTeamId/);
  expect(source).toMatch(/requestTeamId,[\s\S]*requestPluginOptions,[\s\S]*goalForRun/);
});

test("stores Agent Team optimistic session metadata only under plugin options", () => {
  expect(source).not.toMatch(/conversationConfig\.team_id\s*=\s*selectedTeamId/);
  expect(source).not.toMatch(/conversationConfig\.team_id\s*=\s*requestTeamId/);
  expect(source).toMatch(/conversationConfig\.plugin_options = requestPluginOptions/);
  expect(source).toMatch(/isCurrentAgentAvailable,/);
  expect(source).toMatch(/hasAgentCatalogEntryContribution/);
  expect(source).toMatch(/currentSessionOptionContributions,/);
});

test("keeps Team selection writes in the plugin namespace rather than optimistic legacy metadata", () => {
  expect(source).toMatch(/const \[legacyTeamId, setLegacyTeamId\]/);
  expect(source).toMatch(/const selectedTeamId = selectedAgentTeamIdFromMetadata\([\s\S]*plugin_options: sessionPluginOptions,[\s\S]*team_id: legacyTeamId \?\? undefined/);
  expect(source).toMatch(/const \[sessionPluginOptions, setSessionPluginOptions\]/);
  expect(source).toMatch(/const setSessionPluginOption = useCallback/);
  expect(source).toMatch(/setSessionPluginOptions\(\(current\) =>/);
  expect(source).toMatch(/withPluginOption\([\s\S]*pluginId,[\s\S]*key,[\s\S]*value/);
  expect(source).toMatch(/legacyPayloadKeysForPluginOption\(option\)\.includes\("team_id"\)/);
  expect(source).not.toMatch(/isAgentTeamSelectedTeamOption\(pluginId, key\)/);
  expect(source).toMatch(/setLegacyTeamId\(null\)/);
  expect(source).not.toMatch(/selectTeam = useCallback/);
  expect(typesSource).not.toMatch(/selectTeam:/);
  expect(source).toMatch(/requestPluginOptions/);
  expect(source).toMatch(/plugin_options: requestPluginOptions|conversationConfig\.plugin_options = requestPluginOptions/);
  expect(source).not.toMatch(/team_id:\s*requestTeamId/);
  expect(source).not.toMatch(/metadata:\s*{[\s\S]*team_id:\s*selectedTeamId/);
  expect(source).not.toMatch(/submitChat\([\s\S]*team_id:\s*selectedTeamId/);
});
