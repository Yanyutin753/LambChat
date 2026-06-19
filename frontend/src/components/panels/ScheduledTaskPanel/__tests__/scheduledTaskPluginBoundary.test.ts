import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("scheduled task team surfaces depend on Agent Team scheduled task option declarations", () => {
  const panelSource = readFileSync(resolve(__dirname, "../index.tsx"), "utf8");
  const formSource = readFileSync(resolve(__dirname, "../TaskFormModal.tsx"), "utf8");
  const rendererSource = readFileSync(
    resolve(__dirname, "../scheduledTaskOptionRenderers.tsx"),
    "utf8",
  );

  assert.match(panelSource, /useScheduledTaskPluginOptions\(/);
  assert.match(panelSource, /findScheduledTaskOptionRenderer/);
  assert.match(panelSource, /useScheduledTaskOptionValueLabels/);
  assert.match(panelSource, /filterPluginOptionsByVisibleWhen\(scheduledTaskPluginOptions/);
  assert.match(panelSource, /scheduledTaskPluginOptionStringValue/);
  assert.match(panelSource, /legacyPayloadKeysForPluginOption/);
  assert.match(panelSource, /useScheduledTaskPluginOptions\(\s*null,[\s\S]*includeInactive: true/);
  assert.match(formSource, /useScheduledTaskPluginOptions\(agentId,\s*\{[\s\S]*includeInactive: true/);
  assert.match(formSource, /renderScheduledTaskOptionField/);
  assert.match(formSource, /scheduledTaskPluginOptions\.map\(renderScheduledTaskPluginOption\)/);
  assert.match(formSource, /pluginOptionValues: scheduledTaskPluginOptionValues/);
  assert.match(formSource, /pluginOptionDeclarations: scheduledTaskPluginOptions/);
  assert.match(formSource, /setScheduledTaskPluginOptionValue/);
  assert.match(formSource, /hasEffectiveCorePersonaSuppressingOption/);
  assert.match(formSource, /importLegacyPayloadPluginOptions/);
  assert.match(formSource, /retainPluginOptionsForDeclarations/);
  assert.match(formSource, /pluginOptionFromValues/);
  assert.doesNotMatch(formSource, /AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  assert.doesNotMatch(formSource, /selectedAgentTeamOptionValue/);
  assert.doesNotMatch(formSource, /firstEffectivePluginOptionPath/);
  assert.doesNotMatch(formSource, /isAgentTeamAgentId/);
  assert.doesNotMatch(formSource, /setTeamId/);
  assert.doesNotMatch(formSource, /isTeamAgentEffective/);
  assert.doesNotMatch(formSource, /teamAgentAvailable/);
  assert.match(formSource, /Plugin disabled; saved value is retained but will not apply\./);
  assert.match(formSource, /agentOptions\.push\(\{ value: agentId, label: agentId \}\)/);
  assert.match(rendererSource, /teamApi[\s\S]*\.list/);
  assert.match(rendererSource, /"agent_team\.TeamSelectOption"/);
  assert.match(rendererSource, /SCHEDULED_TASK_OPTION_RENDERERS/);
  assert.match(rendererSource, /SCHEDULED_TASK_OPTION_LABEL_RESOLVERS/);
  assert.doesNotMatch(panelSource, /if \(teamAgentAvailable\) \{[\s\S]*teamApi[\s\S]*\.list/);
  assert.doesNotMatch(panelSource, /teamApi/);
  assert.doesNotMatch(panelSource, /hasAgentTeamScheduledTaskOption\(/);
  assert.doesNotMatch(panelSource, /isAgentTeamSelectedTeamOption/);
  assert.doesNotMatch(panelSource, /getScheduledTaskTeamId/);
  assert.doesNotMatch(panelSource, /AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  assert.doesNotMatch(panelSource, /agentTeamTaskOptionDeclared/);
  assert.doesNotMatch(panelSource, /agentTeamTaskOptionAvailable/);
  assert.doesNotMatch(panelSource, /teamAgentAvailable/);
  assert.doesNotMatch(formSource, /teamApi/);
  assert.doesNotMatch(formSource, /hasAgentTeamScheduledTaskOption\(/);
  assert.doesNotMatch(formSource, /if \(teamAgentAvailable\) \{[\s\S]*teamApi[\s\S]*\.list/);
  assert.doesNotMatch(panelSource, /agent\.id === "team"|task\.agent_id === "team"/);
  assert.doesNotMatch(formSource, /agent\.id === "team"|agentId === "team"|v === "team"/);
});
