import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const tabContentSource = readFileSync(
  new URL("../TabContent.tsx", import.meta.url),
  "utf8",
);

function objectLiteral(source: string, name: string): string {
  const match = source.match(new RegExp(`const ${name}[^=]*= \\{([\\s\\S]*?)\\n\\};`));
  assert.ok(match, `${name} object literal should exist`);
  return match[1];
}

test("plugin-owned app panels are not core panel fallbacks", () => {
  const corePanelComponents = objectLiteral(tabContentSource, "corePanelComponents");
  const pluginPanelRenderers = objectLiteral(tabContentSource, "pluginPanelRenderers");

  assert.doesNotMatch(corePanelComponents, /\bfeedback:\s*FeedbackPanel/);
  assert.doesNotMatch(corePanelComponents, /\bteam:\s*TeamBuilderPanel/);
  assert.doesNotMatch(corePanelComponents, /\busage:\s*UsagePanel/);
  assert.doesNotMatch(corePanelComponents, /\bworkflows:\s*WorkflowPanel/);
  assert.doesNotMatch(corePanelComponents, /\b"workflows-editor":\s*WorkflowPanel/);
  assert.doesNotMatch(corePanelComponents, /\b"workflows-run":\s*WorkflowPanel/);

  assert.match(pluginPanelRenderers, /"feedback\.FeedbackPanel":\s*FeedbackPanel/);
  assert.match(pluginPanelRenderers, /"agent_team\.TeamBuilderPanel":\s*TeamBuilderPanel/);
  assert.match(pluginPanelRenderers, /"workflow\.WorkflowPanel":\s*WorkflowPanel/);
  assert.match(pluginPanelRenderers, /"usage_reports\.UsagePanel":\s*UsagePanel/);
  assert.match(tabContentSource, /buildPanelContributions\(runtimePlugins\)/);
});

test("plugin-owned app panels fail closed when renderer is not registered", () => {
  assert.match(tabContentSource, /function PluginPanelUnavailable/);
  assert.match(tabContentSource, /function missingPluginPanelRenderer/);
  assert.match(
    tabContentSource,
    /rendererPanel \?\? corePanel \?\? missingPluginPanelRenderer\(panel\)/,
  );
  assert.match(tabContentSource, /Plugin panel unavailable/);
  assert.match(tabContentSource, /not registered in this build/);
});

test("core agents panel receives runtime plugin state for plugin-owned agent categories", () => {
  assert.match(tabContentSource, /if \(activeTab === "agents"\)/);
  assert.match(tabContentSource, /RuntimeAwareAgentModelPanel/);
  assert.match(tabContentSource, /<RuntimeAwareAgentModelPanel runtimePlugins=\{runtimePlugins\}/);
});

test("workflow plugin panels receive route mode instead of becoming core pages", () => {
  assert.match(
    tabContentSource,
    /activeTab === "workflows" \|\| activeTab === "workflows-editor" \|\| activeTab === "workflows-run"/,
  );
  assert.match(tabContentSource, /WorkflowAwarePanel/);
  assert.match(tabContentSource, /<WorkflowAwarePanel activeTab=\{activeTab\}/);
  assert.doesNotMatch(tabContentSource, /if \(activeTab === "workflows-editor"\)[\s\S]*<Panel \/>/);
  assert.doesNotMatch(tabContentSource, /if \(activeTab === "workflows-run"\)[\s\S]*<Panel \/>/);
});
