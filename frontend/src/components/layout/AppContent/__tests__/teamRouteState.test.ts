import { readFileSync } from "node:fs";
import { getTeamRouteRequest } from "../teamRouteState";

const chatAppContentSource = readFileSync(
  new URL("../ChatAppContent.tsx", import.meta.url),
  "utf8",
);
const pluginOptionsSource = readFileSync(
  new URL("../../../../extensions/pluginOptions.ts", import.meta.url),
  "utf8",
);
const chatViewPropsSource = readFileSync(
  new URL("../ChatViewProps.tsx", import.meta.url),
  "utf8",
);
const chatAssistantIdentityResolversSource = readFileSync(
  new URL("../../../chat/chatAssistantIdentityResolvers.ts", import.meta.url),
  "utf8",
);

test("reads team use requests from chat query params", () => {
  expect(
    getTeamRouteRequest(new URLSearchParams("agent=team&team=team-123"), null),
  ).toEqual({
    agentId: "team",
    teamId: "team-123",
  });
});

test("reads team use requests from route state", () => {
  expect(
    getTeamRouteRequest(new URLSearchParams(), {
      agentId: "team",
      teamId: "team-456",
    }),
  ).toEqual({
    agentId: "team",
    teamId: "team-456",
  });
});

test("ignores incomplete team use requests", () => {
  expect(getTeamRouteRequest(new URLSearchParams("agent=team"), null)).toBe(
    null,
  );
  expect(getTeamRouteRequest(new URLSearchParams("team=team-123"), null)).toBe(
    null,
  );
});

test("chat app applies team route requests to agent and team selection", () => {
  expect(chatAppContentSource).toMatch(
    /getTeamRouteRequest\(searchParams,\s*location\.state\)/,
  );
  expect(chatAppContentSource).toMatch(/hasAgentCatalogEntryContribution\(teamRequest\.agentId, runtimePlugins\)/);
  expect(chatAppContentSource).toMatch(/firstEffectivePluginOptionPath/);
  expect(chatAppContentSource).toMatch(/buildSessionOptionContributions\(runtimePlugins, \{[\s\S]*agentId: teamRequest\.agentId/);
  expect(chatAppContentSource).toMatch(/switchAgent\(teamRequest\.agentId\)/);
  expect(chatAppContentSource).toMatch(/setSessionPluginOption\([\s\S]*optionPath\.pluginId,[\s\S]*optionPath\.key,[\s\S]*teamRequest\.teamId/);
  expect(chatAppContentSource).not.toMatch(/AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
});

test("chat app ignores team route requests when Agent Team is not executable", () => {
  expect(chatAppContentSource).toMatch(/hasAgentCatalogEntryContribution/);
  expect(chatAppContentSource).toMatch(/if \(!hasAgentCatalogEntryContribution\(teamRequest\.agentId, runtimePlugins\)\) \{\s*return;\s*\}/);
  expect(chatAppContentSource).not.toMatch(/switchAgent\(AGENT_TEAM_LEGACY_AGENT_ID\)/);
});

test("chat app persists user team selections through plugin session options", () => {
  expect(chatAppContentSource).toMatch(/buildSessionOptionContributions/);
  expect(chatAppContentSource).toMatch(/isDeclaredEffectiveSessionPluginOption/);
  expect(chatAppContentSource).toMatch(/\.updatePluginOption\(/);
  expect(chatAppContentSource).not.toMatch(/const handleSelectTeam = useCallback/);
  expect(chatAppContentSource).toMatch(/setSessionPluginOption\(pluginId, key, value\);[\s\S]*if \(isDeclaredEffectiveSessionPluginOption\(pluginId, key\)\) \{[\s\S]*persistSessionPluginOption\(pluginId, key, value\)/);
  expect(chatAppContentSource).not.toMatch(/persistAgentTeamSessionOption/);
  expect(chatAppContentSource).not.toMatch(/pluginId === AGENT_TEAM_PLUGIN_ID && key === AGENT_TEAM_SELECTED_TEAM_OPTION/);
  expect(chatAppContentSource).toMatch(/const handlePluginOptionChange = useCallback/);
  expect(chatAppContentSource).toMatch(/onPluginOptionChange=\{handlePluginOptionChange\}/);
  expect(chatAppContentSource).not.toMatch(/onSelectTeam=\{handleSelectTeam\}/);
  expect(chatViewPropsSource).not.toMatch(/onSelectTeam:/);
});

test("chat app restores selected team from plugin session options before legacy team_id", () => {
  expect(pluginOptionsSource).toMatch(/AGENT_TEAM_PLUGIN_ID = "agent_team"/);
  expect(pluginOptionsSource).toMatch(/AGENT_TEAM_SELECTED_TEAM_OPTION = "SELECTED_TEAM_ID"/);
  expect(pluginOptionsSource).toMatch(/metadata\?\.team_id/);
  expect(chatAppContentSource).not.toMatch(/selectTeam\(selectedTeamId\)/);
});

test("new team sessions include plugin session options in optimistic metadata", () => {
  const useAgentSource = readFileSync(
    new URL("../../../../hooks/useAgent.ts", import.meta.url),
    "utf8",
  );
  expect(useAgentSource).toMatch(/const currentSessionOptionContributions = useMemo/);
  expect(useAgentSource).toMatch(/buildSessionOptionContributions\(options\?\.runtimePlugins/);
  expect(useAgentSource).toMatch(/retainPluginOptionsForDeclarations\([\s\S]*sessionOptionSeed,[\s\S]*currentSessionOptionContributions[\s\S]*\)/);
  expect(useAgentSource).toMatch(/const canUseLegacyTeamField =[\s\S]*hasAgentCatalogEntryContribution\(currentAgent, options\?\.runtimePlugins\)/);
  expect(useAgentSource).toMatch(/conversationConfig\.plugin_options = requestPluginOptions/);
  expect(useAgentSource).not.toMatch(/conversationConfig\.team_id\s*=/);
  expect(useAgentSource).not.toMatch(/canUseCurrentTeamAgent/);
  expect(useAgentSource).not.toMatch(/currentAgent === AGENT_TEAM_LEGACY_AGENT_ID/);
});

test("chat app switches team mode back to a persona-compatible agent when using a persona", () => {
  expect(chatAppContentSource).toMatch(/resolvePersonaAgentId/);
  expect(chatAppContentSource).toMatch(
    /const switchToPersonaAgentMode = useCallback/,
  );
  expect(chatAppContentSource).toMatch(/hasAgentCatalogEntryContribution\(currentAgent, runtimePlugins\)/);
  expect(chatAppContentSource).toMatch(/resolvePersonaAgentId\(currentAgent, undefined, agents, \[currentAgent\]\)/);
  expect(chatAppContentSource).not.toMatch(/currentAgent !== AGENT_TEAM_LEGACY_AGENT_ID/);
  expect(chatAppContentSource).toMatch(/sessionOptionContributions[\s\S]*\.filter\(\(option\) => option\.effective\)[\s\S]*handlePluginOptionChange\(option\.pluginId, option\.key, null\)/);
  expect(chatAppContentSource).toMatch(/switchToPersonaAgentMode\(\);[\s\S]*setPersonaPreset\(preset\.id, snapshot\)/);
});

test("chat assistant team identity uses centralized Agent Team plugin constants", () => {
  expect(chatViewPropsSource).toMatch(/usePluginChatAssistantIdentity/);
  expect(chatViewPropsSource).not.toMatch(/selectedAgentTeamIdFromMetadata/);
  expect(chatViewPropsSource).toMatch(/pluginOptionValues: PluginOptionsMetadata/);
  expect(chatAssistantIdentityResolversSource).not.toMatch(/AGENT_TEAM_LEGACY_AGENT_ID/);
  expect(chatAssistantIdentityResolversSource).toMatch(/contribution\.agentId !== currentAgent/);
  expect(chatAssistantIdentityResolversSource).toMatch(/pluginOptionValues\?: PluginOptionsMetadata/);
  expect(chatAssistantIdentityResolversSource).toMatch(/buildAssistantIdentityResolverContributions/);
  expect(chatAssistantIdentityResolversSource).toMatch(/agent_team\.TeamAssistantIdentity/);
  expect(chatViewPropsSource).not.toMatch(/plugin_id === "agent_team"/);
  expect(chatViewPropsSource).not.toMatch(/plugin\?\.enabled && plugin\.executable/);
  expect(chatViewPropsSource).not.toMatch(/currentAgent !== "team"/);
  expect(chatViewPropsSource).not.toMatch(/currentAgent === "team"/);
  expect(chatAssistantIdentityResolversSource).not.toMatch(/plugin_id === "agent_team"/);
  expect(chatAssistantIdentityResolversSource).not.toMatch(/plugin\?\.enabled && plugin\.executable/);
});
