import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const panelSource = readFileSync(
  new URL("../AgentModelPanel.tsx", import.meta.url),
  "utf8",
);
const agentSectionSource = readFileSync(
  new URL("../AgentSection.tsx", import.meta.url),
  "utf8",
);
const globalAgentTabSource = readFileSync(
  new URL("../../AgentPanel/tabs/GlobalAgentTab.tsx", import.meta.url),
  "utf8",
);
const rolesAgentTabSource = readFileSync(
  new URL("../../AgentPanel/tabs/RolesAgentTab.tsx", import.meta.url),
  "utf8",
);
const rolesModelTabSource = readFileSync(
  new URL("../../ModelPanel/tabs/RolesModelTab.tsx", import.meta.url),
  "utf8",
);

test("agent model panel uses a compact console layout", () => {
  assert.match(panelSource, /glass-shell flex h-full flex-col min-h-0/);
  assert.match(panelSource, /agent-model-section-switcher/);
  assert.match(agentSectionSource, /animate-glass-enter/);
});

test("agent and model assignment rows use compact scan-friendly lists", () => {
  assert.match(globalAgentTabSource, /groupAgentsByPluginCategory\(localAgents, agentCategories\)/);
  assert.match(rolesAgentTabSource, /groupAgentsByPluginCategory/);
  assert.match(rolesModelTabSource, /agent-config-list/);
});

test("combined agent model panel preserves plugin-owned agent category boundaries", () => {
  assert.match(panelSource, /runtimePlugins\?: PluginRuntimeContributionStates/);
  assert.match(panelSource, /<AgentSection runtimePlugins=\{runtimePlugins\}/);
  assert.match(agentSectionSource, /buildAgentCategoryContributions\(runtimePlugins\)/);
  assert.match(agentSectionSource, /agentCategories=\{agentCategories\}/);
  assert.match(agentSectionSource, /groupAgentsByPluginCategory\(availableAgents, agentCategories\)/);
  assert.match(agentSectionSource, /category: a\.category/);
});
