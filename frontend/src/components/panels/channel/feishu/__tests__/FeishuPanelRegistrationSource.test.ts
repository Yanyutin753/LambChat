import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

const panelSource = readFileSync(
  new URL("../FeishuPanel.tsx", import.meta.url),
  "utf8",
);
const formSource = readFileSync(
  new URL("../FeishuPanelForm.tsx", import.meta.url),
  "utf8",
);
const channelTypesSource = readFileSync(
  new URL("../../../../../types/channel.ts", import.meta.url),
  "utf8",
);
const channelAgentSelectSource = readFileSync(
  new URL("../../ChannelAgentSelect.tsx", import.meta.url),
  "utf8",
);

test("registration polling cleanup cancels active server-side session", () => {
  assert.match(panelSource, /cancelFeishuRegistration/);
  assert.match(
    panelSource,
    /channelApi\s*\.\s*cancelFeishuRegistration\(\s*registrationSessionId\s*\)/,
  );
  assert.match(panelSource, /return\s+\(\)\s*=>\s*\{/);
});

test("feishu panel uses the bot message icon", () => {
  assert.match(panelSource, /BotMessageSquare/);
  assert.doesNotMatch(panelSource, /import \{[^}]*\bMessageSquare\b/);
});

test("feishu channel form wires persona preset selection through save payloads", () => {
  assert.match(formSource, /ChannelPersonaSelect/);
  assert.match(formSource, /personaPresetId/);
  assert.match(
    panelSource,
    /const\s+\[personaPresetId,\s*setPersonaPresetId\]/,
  );
  assert.match(panelSource, /corePersonaPresetForChannelConfig\([\s\S]*initialAgentId/);
  assert.match(panelSource, /config\.persona_preset_id \|\| null/);
  assert.match(panelSource, /channelPersonaPresetId/);
  assert.match(panelSource, /persona_preset_id:\s*channelPersonaPresetId/);
  assert.match(channelTypesSource, /persona_preset_id\?: string \| null/);
});

test("feishu channel form switches persona visibility through plugin option declarations", () => {
  assert.match(formSource, /ChannelPluginOptions/);
  assert.doesNotMatch(formSource, /import \{ ChannelTeamSelect \}/);
  assert.doesNotMatch(formSource, /const selectedAgentTeam = isAgentTeamAgentId\(agentId\)/);
  assert.doesNotMatch(formSource, /const usesAgentTeam = teamAgentAvailable && selectedAgentTeam/);
  assert.match(formSource, /effectiveChannelPluginOptions/);
  assert.match(formSource, /hasEffectiveCorePersonaSuppressingOption/);
  assert.match(formSource, /const suppressesCorePersonaSelector = hasEffectiveCorePersonaSuppressingOption/);
  assert.match(formSource, /channelPluginOptionValues/);
  assert.match(formSource, /setChannelPluginOption/);
  assert.doesNotMatch(panelSource, /const\s+\[teamId,\s*setTeamId\]/);
  assert.doesNotMatch(panelSource, /const\s+\[availableAgents,\s*setAvailableAgents\]/);
  assert.match(panelSource, /useChannelPluginOptions\("feishu",\s*\{[\s\S]*includeInactive: true/);
  assert.match(formSource, /filterPluginOptionsByVisibleWhen/);
  assert.match(formSource, /agentId,/);
  assert.match(formSource, /route:\s*"\/channels\/feishu"/);
  assert.match(formSource, /scope:\s*"channel"/);
  assert.doesNotMatch(panelSource, /hasAgentTeamChannelOptionDeclaration/);
  assert.doesNotMatch(panelSource, /hasAgentTeamChannelOption\(/);
  assert.doesNotMatch(panelSource, /isAgentTeamAgentAvailable/);
  assert.doesNotMatch(formSource, /agentTeamChannelOptionDeclared/);
  assert.match(panelSource, /pluginOptionsForChannelConfig/);
  assert.match(panelSource, /importLegacyPayloadPluginOptions/);
  assert.match(panelSource, /pluginOptionsFromMetadata/);
  assert.match(panelSource, /withPluginOption/);
  assert.match(panelSource, /retainPluginOptionsForDeclarations/);
  assert.match(panelSource, /filterPluginOptionsByVisibleWhen/);
  assert.match(panelSource, /corePersonaPresetForChannelConfig/);
  assert.match(panelSource, /hasEffectiveCorePersonaSuppressingOption/);
  assert.doesNotMatch(panelSource, /selectedAgentTeamIdFromMetadata/);
  assert.doesNotMatch(panelSource, /AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  assert.doesNotMatch(panelSource, /agentTeamSessionPluginOptions/);
  assert.doesNotMatch(panelSource, /channelTeamId/);
  assert.doesNotMatch(panelSource, /const channelPluginOptions = channelUsesAgentTeam/);
  assert.match(panelSource, /channelPluginOptionValues/);
  assert.match(panelSource, /setChannelPluginOptionValues/);
  assert.match(panelSource, /handleChannelPluginOptionChange/);
  assert.doesNotMatch(panelSource, /const channelUsesAgentTeam = isAgentTeamAgentId\(agentId\)/);
  assert.doesNotMatch(panelSource, /isAgentTeamAgentId/);
  assert.doesNotMatch(panelSource, /team_id:\s*channelTeamId/);
  assert.match(panelSource, /plugin_options:\s*nextChannelPluginOptions/);
  assert.match(panelSource, /setPersonaPresetId\(null\)/);
  assert.doesNotMatch(panelSource, /setTeamId\(/);
  assert.match(channelAgentSelectSource, /onAgentsLoaded\?: \(agents: AgentInfo\[\]\) => void/);
  assert.match(channelAgentSelectSource, /onAgentsLoaded\?\.\(nextAgents\)/);
  assert.doesNotMatch(formSource, /onAgentsLoaded=\{setAvailableAgents\}/);
  assert.match(channelTypesSource, /team_id\?: string \| null/);
  assert.match(channelTypesSource, /plugin_options\?: Record<string, Record<string, unknown>> \| null/);
  assert.doesNotMatch(panelSource, /agent\.id === "team"|initialAgentId === "team"|loadedAgentId === "team"|value === "team"|agentId === "team"/);
  assert.doesNotMatch(formSource, /agentId === "team"/);
});
