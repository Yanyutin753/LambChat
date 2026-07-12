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
  expect(panelSource).toMatch(/cancelFeishuRegistration/);
  expect(panelSource).toMatch(
    /channelApi\s*\.\s*cancelFeishuRegistration\(\s*registrationSessionId\s*\)/,
  );
  expect(panelSource).toMatch(/return\s+\(\)\s*=>\s*\{/);
});

test("feishu panel uses the bot message icon", () => {
  expect(panelSource).toMatch(/BotMessageSquare/);
  expect(panelSource).not.toMatch(/import \{[^}]*\bMessageSquare\b/);
});

test("feishu channel form wires persona preset selection through save payloads", () => {
  expect(formSource).toMatch(/ChannelPersonaSelect/);
  expect(formSource).toMatch(/personaPresetId/);
  expect(panelSource).toMatch(
    /const\s+\[personaPresetId,\s*setPersonaPresetId\]/,
  );
  expect(panelSource).toMatch(/corePersonaPresetForChannelConfig\([\s\S]*initialAgentId/);
  expect(panelSource).toMatch(/config\.persona_preset_id \|\| null/);
  expect(panelSource).toMatch(/channelPersonaPresetId/);
  expect(panelSource).toMatch(/persona_preset_id:\s*channelPersonaPresetId/);
  expect(channelTypesSource).toMatch(/persona_preset_id\?: string \| null/);
});

test("feishu channel form switches persona visibility through plugin option declarations", () => {
  expect(formSource).toMatch(/ChannelPluginOptions/);
  expect(formSource).not.toMatch(/import \{ ChannelTeamSelect \}/);
  expect(formSource).not.toMatch(/const selectedAgentTeam = isAgentTeamAgentId\(agentId\)/);
  expect(formSource).not.toMatch(/const usesAgentTeam = teamAgentAvailable && selectedAgentTeam/);
  expect(formSource).toMatch(/effectiveChannelPluginOptions/);
  expect(formSource).toMatch(/hasEffectiveCorePersonaSuppressingOption/);
  expect(formSource).toMatch(/const suppressesCorePersonaSelector = hasEffectiveCorePersonaSuppressingOption/);
  expect(formSource).toMatch(/channelPluginOptionValues/);
  expect(formSource).toMatch(/setChannelPluginOption/);
  expect(panelSource).not.toMatch(/const\s+\[teamId,\s*setTeamId\]/);
  expect(panelSource).not.toMatch(/const\s+\[availableAgents,\s*setAvailableAgents\]/);
  expect(panelSource).toMatch(/useChannelPluginOptions\("feishu",\s*\{[\s\S]*includeInactive: true/);
  expect(formSource).toMatch(/filterPluginOptionsByVisibleWhen/);
  expect(formSource).toMatch(/agentId,/);
  expect(formSource).toMatch(/route:\s*"\/channels\/feishu"/);
  expect(formSource).toMatch(/scope:\s*"channel"/);
  expect(panelSource).not.toMatch(/hasAgentTeamChannelOptionDeclaration/);
  expect(panelSource).not.toMatch(/hasAgentTeamChannelOption\(/);
  expect(panelSource).not.toMatch(/isAgentTeamAgentAvailable/);
  expect(formSource).not.toMatch(/agentTeamChannelOptionDeclared/);
  expect(panelSource).toMatch(/pluginOptionsForChannelConfig/);
  expect(panelSource).toMatch(/importLegacyPayloadPluginOptions/);
  expect(panelSource).toMatch(/pluginOptionsFromMetadata/);
  expect(panelSource).toMatch(/withPluginOption/);
  expect(panelSource).toMatch(/retainPluginOptionsForDeclarations/);
  expect(panelSource).toMatch(/filterPluginOptionsByVisibleWhen/);
  expect(panelSource).toMatch(/corePersonaPresetForChannelConfig/);
  expect(panelSource).toMatch(/hasEffectiveCorePersonaSuppressingOption/);
  expect(panelSource).not.toMatch(/selectedAgentTeamIdFromMetadata/);
  expect(panelSource).not.toMatch(/AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  expect(panelSource).not.toMatch(/agentTeamSessionPluginOptions/);
  expect(panelSource).not.toMatch(/channelTeamId/);
  expect(panelSource).not.toMatch(/const channelPluginOptions = channelUsesAgentTeam/);
  expect(panelSource).toMatch(/channelPluginOptionValues/);
  expect(panelSource).toMatch(/setChannelPluginOptionValues/);
  expect(panelSource).toMatch(/handleChannelPluginOptionChange/);
  expect(panelSource).not.toMatch(/const channelUsesAgentTeam = isAgentTeamAgentId\(agentId\)/);
  expect(panelSource).not.toMatch(/isAgentTeamAgentId/);
  expect(panelSource).not.toMatch(/team_id:\s*channelTeamId/);
  expect(panelSource).toMatch(/plugin_options:\s*nextChannelPluginOptions/);
  expect(panelSource).toMatch(/setPersonaPresetId\(null\)/);
  expect(panelSource).not.toMatch(/setTeamId\(/);
  expect(channelAgentSelectSource).toMatch(/onAgentsLoaded\?: \(agents: AgentInfo\[\]\) => void/);
  expect(channelAgentSelectSource).toMatch(/onAgentsLoaded\?\.\(nextAgents\)/);
  expect(formSource).not.toMatch(/onAgentsLoaded=\{setAvailableAgents\}/);
  expect(channelTypesSource).toMatch(/team_id\?: string \| null/);
  expect(channelTypesSource).toMatch(/plugin_options\?: Record<string, Record<string, unknown>> \| null/);
  expect(panelSource).not.toMatch(/agent\.id === "team"|initialAgentId === "team"|loadedAgentId === "team"|value === "team"|agentId === "team"/);
  expect(formSource).not.toMatch(/agentId === "team"/);
});

test("feishu agent selection retains visible plugin options and clears suppressed persona state", () => {
  expect(panelSource).toMatch(
    /const\s+handleAgentIdChange\s*=\s*\(value:\s*string\s*\|\s*null\)\s*=>\s*\{[\s\S]*?setAgentId\(value\);[\s\S]*?filterPluginOptionsByVisibleWhen\(channelPluginOptions,\s*\{[\s\S]*?agentId:\s*value,[\s\S]*?route:\s*"\/channels\/feishu"[\s\S]*?scope:\s*"channel"[\s\S]*?\}\)/,
  );
  expect(panelSource).toMatch(
    /setChannelPluginOptionValues\(\(current\) =>[\s\S]*retainPluginOptionsForDeclarations\(current,\s*nextOptions\)/,
  );
  expect(panelSource).toMatch(
    /nextOptions\.some\([\s\S]*suppresses_core_persona_selector[\s\S]*setPersonaPresetId\(null\)/,
  );
  expect(panelSource).toMatch(/onAgentIdChange=\{handleAgentIdChange\}/);
  expect(panelSource).toMatch(/setPersonaPresetId=\{setPersonaPresetId\}/);
  expect(formSource).toMatch(
    /onAgentIdChange:\s*\(value:\s*string\s*\|\s*null\)\s*=>\s*void/,
  );
  expect(formSource).toMatch(
    /ChannelAgentSelect value=\{agentId\} onChange=\{onAgentIdChange\}/,
  );
  expect(formSource).not.toMatch(
    /ChannelAgentSelect value=\{agentId\} onChange=\{setAgentId\}/,
  );
});
