import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
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
  assert.deepEqual(
    getTeamRouteRequest(new URLSearchParams("agent=team&team=team-123"), null),
    {
      agentId: "team",
      teamId: "team-123",
    },
  );
});

test("reads team use requests from route state", () => {
  assert.deepEqual(
    getTeamRouteRequest(new URLSearchParams(), {
      agentId: "team",
      teamId: "team-456",
    }),
    {
      agentId: "team",
      teamId: "team-456",
    },
  );
});

test("ignores incomplete team use requests", () => {
  assert.equal(
    getTeamRouteRequest(new URLSearchParams("agent=team"), null),
    null,
  );
  assert.equal(
    getTeamRouteRequest(new URLSearchParams("team=team-123"), null),
    null,
  );
});

test("chat app applies team route requests to agent and team selection", () => {
  assert.match(
    chatAppContentSource,
    /getTeamRouteRequest\(searchParams,\s*location\.state\)/,
  );
  assert.match(chatAppContentSource, /hasAgentCatalogEntryContribution\(teamRequest\.agentId, runtimePlugins\)/);
  assert.match(chatAppContentSource, /firstEffectivePluginOptionPath/);
  assert.match(
    chatAppContentSource,
    /buildSessionOptionContributions\(runtimePlugins, \{[\s\S]*agentId: teamRequest\.agentId/,
  );
  assert.match(chatAppContentSource, /switchAgent\(teamRequest\.agentId\)/);
  assert.match(
    chatAppContentSource,
    /setSessionPluginOption\([\s\S]*optionPath\.pluginId,[\s\S]*optionPath\.key,[\s\S]*teamRequest\.teamId/,
  );
  assert.doesNotMatch(chatAppContentSource, /AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
});

test("chat app ignores team route requests when Agent Team is not executable", () => {
  assert.match(chatAppContentSource, /hasAgentCatalogEntryContribution/);
  assert.match(
    chatAppContentSource,
    /if \(!hasAgentCatalogEntryContribution\(teamRequest\.agentId, runtimePlugins\)\) \{\s*return;\s*\}/,
  );
  assert.doesNotMatch(chatAppContentSource, /switchAgent\(AGENT_TEAM_LEGACY_AGENT_ID\)/);
});

test("chat app persists user team selections through plugin session options", () => {
  assert.match(chatAppContentSource, /buildSessionOptionContributions/);
  assert.match(chatAppContentSource, /isDeclaredEffectiveSessionPluginOption/);
  assert.match(chatAppContentSource, /\.updatePluginOption\(/);
  assert.doesNotMatch(chatAppContentSource, /const handleSelectTeam = useCallback/);
  assert.match(
    chatAppContentSource,
    /setSessionPluginOption\(pluginId, key, value\);[\s\S]*if \(isDeclaredEffectiveSessionPluginOption\(pluginId, key\)\) \{[\s\S]*persistSessionPluginOption\(pluginId, key, value\)/,
  );
  assert.doesNotMatch(chatAppContentSource, /persistAgentTeamSessionOption/);
  assert.doesNotMatch(
    chatAppContentSource,
    /pluginId === AGENT_TEAM_PLUGIN_ID && key === AGENT_TEAM_SELECTED_TEAM_OPTION/,
  );
  assert.match(chatAppContentSource, /const handlePluginOptionChange = useCallback/);
  assert.match(chatAppContentSource, /onPluginOptionChange=\{handlePluginOptionChange\}/);
  assert.doesNotMatch(chatAppContentSource, /onSelectTeam=\{handleSelectTeam\}/);
  assert.doesNotMatch(chatViewPropsSource, /onSelectTeam:/);
});

test("chat app restores selected team from plugin session options before legacy team_id", () => {
  assert.match(pluginOptionsSource, /AGENT_TEAM_PLUGIN_ID = "agent_team"/);
  assert.match(pluginOptionsSource, /AGENT_TEAM_SELECTED_TEAM_OPTION = "SELECTED_TEAM_ID"/);
  assert.match(pluginOptionsSource, /metadata\?\.team_id/);
  assert.doesNotMatch(chatAppContentSource, /selectTeam\(selectedTeamId\)/);
});

test("new team sessions include plugin session options in optimistic metadata", () => {
  const useAgentSource = readFileSync(
    new URL("../../../../hooks/useAgent.ts", import.meta.url),
    "utf8",
  );
  assert.match(useAgentSource, /const currentSessionOptionContributions = useMemo/);
  assert.match(useAgentSource, /buildSessionOptionContributions\(options\?\.runtimePlugins/);
  assert.match(
    useAgentSource,
    /retainPluginOptionsForDeclarations\([\s\S]*sessionOptionSeed,[\s\S]*currentSessionOptionContributions[\s\S]*\)/,
  );
  assert.match(
    useAgentSource,
    /const canUseLegacyTeamField =[\s\S]*hasAgentCatalogEntryContribution\(currentAgent, options\?\.runtimePlugins\)/,
  );
  assert.match(useAgentSource, /conversationConfig\.plugin_options = requestPluginOptions/);
  assert.doesNotMatch(useAgentSource, /conversationConfig\.team_id\s*=/);
  assert.doesNotMatch(useAgentSource, /canUseCurrentTeamAgent/);
  assert.doesNotMatch(useAgentSource, /currentAgent === AGENT_TEAM_LEGACY_AGENT_ID/);
});

test("chat app switches team mode back to a persona-compatible agent when using a persona", () => {
  assert.match(chatAppContentSource, /resolvePersonaAgentId/);
  assert.match(
    chatAppContentSource,
    /const switchToPersonaAgentMode = useCallback/,
  );
  assert.match(chatAppContentSource, /hasAgentCatalogEntryContribution\(currentAgent, runtimePlugins\)/);
  assert.match(chatAppContentSource, /resolvePersonaAgentId\(currentAgent, undefined, agents, \[currentAgent\]\)/);
  assert.doesNotMatch(chatAppContentSource, /currentAgent !== AGENT_TEAM_LEGACY_AGENT_ID/);
  assert.match(
    chatAppContentSource,
    /sessionOptionContributions[\s\S]*\.filter\(\(option\) => option\.effective\)[\s\S]*handlePluginOptionChange\(option\.pluginId, option\.key, null\)/,
  );
  assert.match(
    chatAppContentSource,
    /switchToPersonaAgentMode\(\);[\s\S]*setPersonaPreset\(preset\.id, snapshot\)/,
  );
});

test("chat assistant team identity uses centralized Agent Team plugin constants", () => {
  assert.match(chatViewPropsSource, /usePluginChatAssistantIdentity/);
  assert.doesNotMatch(chatViewPropsSource, /selectedAgentTeamIdFromMetadata/);
  assert.match(chatViewPropsSource, /pluginOptionValues: PluginOptionsMetadata/);
  assert.doesNotMatch(chatAssistantIdentityResolversSource, /AGENT_TEAM_LEGACY_AGENT_ID/);
  assert.match(chatAssistantIdentityResolversSource, /contribution\.agentId !== currentAgent/);
  assert.match(chatAssistantIdentityResolversSource, /pluginOptionValues\?: PluginOptionsMetadata/);
  assert.match(chatAssistantIdentityResolversSource, /buildAssistantIdentityResolverContributions/);
  assert.match(chatAssistantIdentityResolversSource, /agent_team\.TeamAssistantIdentity/);
  assert.doesNotMatch(chatViewPropsSource, /plugin_id === "agent_team"/);
  assert.doesNotMatch(chatViewPropsSource, /plugin\?\.enabled && plugin\.executable/);
  assert.doesNotMatch(chatViewPropsSource, /currentAgent !== "team"/);
  assert.doesNotMatch(chatViewPropsSource, /currentAgent === "team"/);
  assert.doesNotMatch(chatAssistantIdentityResolversSource, /plugin_id === "agent_team"/);
  assert.doesNotMatch(chatAssistantIdentityResolversSource, /plugin\?\.enabled && plugin\.executable/);
});
