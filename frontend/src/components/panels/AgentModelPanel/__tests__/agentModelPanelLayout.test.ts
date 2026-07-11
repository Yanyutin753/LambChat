import { readFileSync } from "node:fs";
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
  expect(panelSource).toMatch(/glass-shell flex h-full flex-col min-h-0/);
  expect(panelSource).toMatch(/agent-model-section-switcher/);
  expect(agentSectionSource).toMatch(/animate-glass-enter/);
});

test("agent and model assignment rows use compact scan-friendly lists", () => {
  expect(globalAgentTabSource).toMatch(/groupAgentsByPluginCategory\(localAgents, agentCategories\)/);
  expect(rolesAgentTabSource).toMatch(/groupAgentsByPluginCategory/);
  expect(rolesModelTabSource).toMatch(/agent-config-list/);
});

test("combined agent model panel preserves plugin-owned agent category boundaries", () => {
  expect(panelSource).toMatch(/runtimePlugins\?: PluginRuntimeContributionStates/);
  expect(panelSource).toMatch(/<AgentSection runtimePlugins=\{runtimePlugins\}/);
  expect(agentSectionSource).toMatch(/buildAgentCategoryContributions\(runtimePlugins\)/);
  expect(agentSectionSource).toMatch(/agentCategories=\{agentCategories\}/);
  expect(agentSectionSource).toMatch(/groupAgentsByPluginCategory\(availableAgents, agentCategories\)/);
  expect(agentSectionSource).toMatch(/category: a\.category/);
});
