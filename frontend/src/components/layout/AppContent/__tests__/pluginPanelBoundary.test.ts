import { readFileSync } from "node:fs";
import { test } from "vitest";

const tabContentSource = readFileSync(
  new URL("../TabContent.tsx", import.meta.url),
  "utf8",
);

function objectLiteral(source: string, name: string): string {
  const match = source.match(new RegExp(`const ${name}[^=]*= \\{([\\s\\S]*?)\\n\\};`));
  expect(match).toBeTruthy();
  return match[1];
}

test("plugin-owned app panels are not core panel fallbacks", () => {
  const corePanelComponents = objectLiteral(tabContentSource, "corePanelComponents");
  const pluginPanelRenderers = objectLiteral(tabContentSource, "pluginPanelRenderers");

  expect(corePanelComponents).not.toMatch(/\bfeedback:\s*FeedbackPanel/);
  expect(corePanelComponents).not.toMatch(/\bteam:\s*TeamBuilderPanel/);
  expect(corePanelComponents).not.toMatch(/\busage:\s*UsagePanel/);

  expect(pluginPanelRenderers).toMatch(/"feedback\.FeedbackPanel":\s*FeedbackPanel/);
  expect(pluginPanelRenderers).toMatch(/"agent_team\.TeamBuilderPanel":\s*TeamBuilderPanel/);
  expect(pluginPanelRenderers).toMatch(/"usage_reports\.UsagePanel":\s*UsagePanel/);
  expect(tabContentSource).toMatch(/buildPanelContributions\(runtimePlugins\)/);
});

test("plugin-owned app panels fail closed when renderer is not registered", () => {
  expect(tabContentSource).toMatch(/function PluginPanelUnavailable/);
  expect(tabContentSource).toMatch(/function missingPluginPanelRenderer/);
  expect(tabContentSource).toMatch(/rendererPanel \?\? corePanel \?\? missingPluginPanelRenderer\(panel\)/);
  expect(tabContentSource).toMatch(/Plugin panel unavailable/);
  expect(tabContentSource).toMatch(/not registered in this build/);
});

test("core agents panel receives runtime plugin state for plugin-owned agent categories", () => {
  expect(tabContentSource).toMatch(/agents:\s*AgentModelPanel/);
  expect(tabContentSource).toMatch(/type RuntimeAwarePanelProps/);
  expect(tabContentSource).toMatch(/runtimePlugins\?: PluginRuntimeContributionStates/);
  expect(tabContentSource).toMatch(/function renderPanel/);
  expect(tabContentSource).toMatch(/<Panel activeTab=\{activeTab\} runtimePlugins=\{runtimePlugins\} \/>/);
});
