import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("scheduled task team surfaces depend on Agent Team scheduled task option declarations", () => {
  const panelSource = readFileSync(resolve(__dirname, "../index.tsx"), "utf8");
  const formSource = readFileSync(resolve(__dirname, "../TaskFormModal.tsx"), "utf8");
  const rendererSource = readFileSync(
    resolve(__dirname, "../scheduledTaskOptionRenderers.tsx"),
    "utf8",
  );
  const taskSessionListSource = readFileSync(resolve(__dirname, "../TaskSessionList.tsx"), "utf8");

  expect(panelSource).toMatch(/useScheduledTaskPluginOptions\(/);
  expect(panelSource).toMatch(/findScheduledTaskOptionRenderer/);
  expect(panelSource).toMatch(/useScheduledTaskOptionValueLabels/);
  expect(panelSource).toMatch(/filterPluginOptionsByVisibleWhen\(scheduledTaskPluginOptions/);
  expect(panelSource).toMatch(/scheduledTaskPluginOptionStringValue/);
  expect(panelSource).toMatch(/legacyPayloadKeysForPluginOption/);
  expect(panelSource).toMatch(/useScheduledTaskPluginOptions\(\s*null,[\s\S]*includeInactive: true/);
  expect(formSource).toMatch(/useScheduledTaskPluginOptions\(agentId,\s*\{[\s\S]*includeInactive: true/);
  expect(formSource).toMatch(/renderScheduledTaskOptionField/);
  expect(formSource).toMatch(/scheduledTaskPluginOptions\.map\(renderScheduledTaskPluginOption\)/);
  expect(formSource).toMatch(/pluginOptionValues: scheduledTaskPluginOptionValues/);
  expect(formSource).toMatch(/pluginOptionDeclarations: scheduledTaskPluginOptions/);
  expect(formSource).toMatch(/setScheduledTaskPluginOptionValue/);
  expect(formSource).toMatch(/hasEffectiveCorePersonaSuppressingOption/);
  expect(formSource).toMatch(/importLegacyPayloadPluginOptions/);
  expect(formSource).toMatch(/retainPluginOptionsForDeclarations/);
  expect(formSource).toMatch(/pluginOptionFromValues/);
  expect(formSource).not.toMatch(/AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  expect(formSource).not.toMatch(/selectedAgentTeamOptionValue/);
  expect(formSource).not.toMatch(/firstEffectivePluginOptionPath/);
  expect(formSource).not.toMatch(/isAgentTeamAgentId/);
  expect(formSource).not.toMatch(/setTeamId/);
  expect(formSource).not.toMatch(/isTeamAgentEffective/);
  expect(formSource).not.toMatch(/teamAgentAvailable/);
  expect(formSource).toMatch(/Plugin disabled; saved value is retained but will not apply\./);
  expect(formSource).toMatch(/agentOptions\.push\(\{ value: agentId, label: agentId \}\)/);
  expect(rendererSource).toMatch(/teamApi[\s\S]*\.list/);
  expect(rendererSource).toMatch(/"agent_team\.TeamSelectOption"/);
  expect(rendererSource).toMatch(/SCHEDULED_TASK_OPTION_RENDERERS/);
  expect(rendererSource).toMatch(/SCHEDULED_TASK_OPTION_LABEL_RESOLVERS/);
  expect(rendererSource).not.toMatch(/WorkflowPlugin/);
  expect(rendererSource).not.toMatch(/workflow\.Workflow/);
  expect(taskSessionListSource).not.toMatch(/workflowResult|workflowOutput|workflowNextAction/);
  expect(taskSessionListSource).not.toMatch(/\/workflows\//);
  expect(panelSource).not.toMatch(/if \(teamAgentAvailable\) \{[\s\S]*teamApi[\s\S]*\.list/);
  expect(panelSource).not.toMatch(/teamApi/);
  expect(panelSource).not.toMatch(/hasAgentTeamScheduledTaskOption\(/);
  expect(panelSource).not.toMatch(/isAgentTeamSelectedTeamOption/);
  expect(panelSource).not.toMatch(/getScheduledTaskTeamId/);
  expect(panelSource).not.toMatch(/AGENT_TEAM_PLUGIN_ID|AGENT_TEAM_SELECTED_TEAM_OPTION/);
  expect(panelSource).not.toMatch(/agentTeamTaskOptionDeclared/);
  expect(panelSource).not.toMatch(/agentTeamTaskOptionAvailable/);
  expect(panelSource).not.toMatch(/teamAgentAvailable/);
  expect(formSource).not.toMatch(/teamApi/);
  expect(formSource).not.toMatch(/hasAgentTeamScheduledTaskOption\(/);
  expect(formSource).not.toMatch(/if \(teamAgentAvailable\) \{[\s\S]*teamApi[\s\S]*\.list/);
  expect(panelSource).not.toMatch(/agent\.id === "team"|task\.agent_id === "team"/);
  expect(formSource).not.toMatch(/agent\.id === "team"|agentId === "team"|v === "team"/);
});
