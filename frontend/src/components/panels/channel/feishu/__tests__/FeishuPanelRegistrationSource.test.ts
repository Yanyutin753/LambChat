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

test("registration polling cleanup cancels active server-side session", () => {
  expect(panelSource).toMatch(/cancelFeishuRegistration/);
  expect(panelSource).toMatch(
    /channelApi\s*\.\s*cancelFeishuRegistration\(\s*registrationSessionId\s*\)/,
  );
  expect(panelSource).toMatch(/return\s+\(\)\s*=>\s*\{/);
});

test("feishu panel uses the shared Feishu brand icon", () => {
  expect(panelSource).toMatch(/<ChannelIcon channelType="feishu"/);
  expect(panelSource).not.toMatch(/import \{[^}]*\bMessageSquare\b/);
});

test("feishu channel form wires persona preset selection through save payloads", () => {
  expect(formSource).toMatch(/ChannelPersonaSelect/);
  expect(formSource).toMatch(/personaPresetId/);
  expect(panelSource).toMatch(
    /const\s+\[personaPresetId,\s*setPersonaPresetId\]/,
  );
  expect(panelSource).toMatch(/initialAgentId === "team"[\s\S]*\? null/);
  expect(panelSource).toMatch(/initialConfig\.persona_preset_id \|\| null/);
  expect(panelSource).toMatch(/channelPersonaPresetId/);
  expect(panelSource).toMatch(/persona_preset_id:\s*channelPersonaPresetId/);
  expect(channelTypesSource).toMatch(/persona_preset_id\?: string \| null/);
});

test("feishu channel form switches from persona to team selection for team agent", () => {
  expect(formSource).toMatch(/ChannelTeamSelect/);
  expect(formSource).toMatch(/agentId\s*===\s*"team"/);
  expect(formSource).toMatch(/teamId/);
  expect(panelSource).toMatch(/const\s+\[teamId,\s*setTeamId\]/);
  expect(panelSource).toMatch(/channelTeamId/);
  expect(panelSource).toMatch(/team_id:\s*channelTeamId/);
  expect(panelSource).toMatch(/setPersonaPresetId\(null\)/);
  expect(panelSource).toMatch(/setTeamId\(null\)/);
  expect(channelTypesSource).toMatch(/team_id\?: string \| null/);
});

test("feishu agent selection clears mutually exclusive team and persona state", () => {
  expect(panelSource).toMatch(
    /const\s+handleAgentIdChange\s*=\s*\(value:\s*string\s*\|\s*null\)\s*=>\s*\{[\s\S]*?setAgentId\(value\);[\s\S]*?if\s*\(value\s*===\s*"team"\)\s*\{[\s\S]*?setPersonaPresetId\(null\);[\s\S]*?\}\s*else\s*\{[\s\S]*?setTeamId\(null\);[\s\S]*?\}/,
  );
  expect(panelSource).toMatch(
    /const\s+handlePersonaPresetIdChange\s*=\s*\(value:\s*string\s*\|\s*null\)\s*=>\s*\{[\s\S]*?setPersonaPresetId\(value\);[\s\S]*?if\s*\(value\)\s*\{[\s\S]*?setTeamId\(null\);[\s\S]*?\}/,
  );
  expect(panelSource).toMatch(/onAgentIdChange=\{handleAgentIdChange\}/);
  expect(panelSource).toMatch(
    /setPersonaPresetId=\{handlePersonaPresetIdChange\}/,
  );
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
