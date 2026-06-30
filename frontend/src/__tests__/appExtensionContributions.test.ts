import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
const hookSource = readFileSync(
  new URL("../hooks/useExtensionContributions.ts", import.meta.url),
  "utf8",
);
const tabContentSource = readFileSync(
  new URL("../components/layout/AppContent/TabContent.tsx", import.meta.url),
  "utf8",
);

test("App consumes extension host contributions instead of plugin runtime management data", () => {
  assert.match(appSource, /useExtensionContributions/);
  assert.match(appSource, /const EMPTY_RUNTIME_PLUGINS/);
  assert.match(appSource, /extensionContributions\?\.plugins \?\? EMPTY_RUNTIME_PLUGINS/);
  assert.match(appSource, /buildAppRouteContributions\(runtimePlugins\)/);
  assert.match(appSource, /runtimePlugins=\{runtimePlugins\}/);
  assert.doesNotMatch(appSource, /usePluginRuntime/);
  assert.doesNotMatch(appSource, /fetchPlugins/);
});

test("plugin-owned app routes are generated from runtime contributions only", () => {
  assert.match(appSource, /appRouteContributions\.map\(\(route\) => \(/);
  assert.match(appSource, /path=\{route\.path\}/);
  assert.doesNotMatch(appSource, /<Route\s+path="\/feedback"/);
  assert.doesNotMatch(appSource, /<Route\s+path="\/team"/);
  assert.doesNotMatch(appSource, /<Route\s+path="\/agent-team"/);
  assert.doesNotMatch(appSource, /<Route\s+path="\/usage"/);
  assert.doesNotMatch(appSource, /path:\s*"\/feedback"|path:\s*"\/team"|path:\s*"\/usage"/);
});

test("plugin-owned app routes show a loading route while contributions load", () => {
  assert.match(appSource, /matchPath/);
  assert.match(appSource, /useLocation\(\)/);
  assert.match(appSource, /isLoading:\s*areExtensionContributionsLoading/);
  assert.match(appSource, /BUILTIN_PLUGIN_APP_ROUTE_LOADING_PATHS/);
  assert.match(appSource, /"\/agent-team"/);
  assert.match(appSource, /"\/workflows"/);
  assert.match(appSource, /"\/workflows\/:workflowId\/editor"/);
  assert.match(appSource, /"\/workflows\/:workflowId\/runs\/:runId"/);
  assert.doesNotMatch(appSource, /"\/team"/);
  assert.match(appSource, /shouldShowPluginRouteLoading/);
  assert.match(appSource, /matchPath\(\{ path, end: true \}, location\.pathname\)/);
  assert.match(appSource, /path=\{location\.pathname\}/);
  assert.match(appSource, /<ChatPageSkeleton \/>/);
});

test("Workflow routes and panel stay plugin-owned", () => {
  assert.doesNotMatch(appSource, /workflowFallbackRoutes/);
  assert.doesNotMatch(appSource, /missingWorkflowFallbackRoutes/);
  assert.doesNotMatch(appSource, /pluginId: "workflow"/);
  assert.doesNotMatch(tabContentSource, /workflows: WorkflowPanel/);
  assert.match(tabContentSource, /"workflow\.WorkflowPanel": WorkflowPanel/);
  assert.match(tabContentSource, /activeTab === "workflows"/);
  assert.match(tabContentSource, /activeTab === "workflows-editor"/);
  assert.match(tabContentSource, /activeTab === "workflows-run"/);
});

test("extension contribution hook uses the lightweight host endpoint and runtime update event", () => {
  assert.match(hookSource, /pluginRuntimeApi\.listContributions\(\)/);
  assert.match(hookSource, /listenPluginRuntimeUpdated/);
  assert.doesNotMatch(hookSource, /pluginRuntimeApi\.list\(\)/);
});
