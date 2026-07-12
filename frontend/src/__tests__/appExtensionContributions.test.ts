import { readFileSync } from "node:fs";
import { test } from "vitest";

const appSource = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
const hookSource = readFileSync(
  new URL("../hooks/useExtensionContributions.ts", import.meta.url),
  "utf8",
);

test("App consumes extension host contributions instead of plugin runtime management data", () => {
  expect(appSource).toMatch(/useExtensionContributions/);
  expect(appSource).toMatch(/const EMPTY_RUNTIME_PLUGINS/);
  expect(appSource).toMatch(/extensionContributions\?\.plugins \?\? EMPTY_RUNTIME_PLUGINS/);
  expect(appSource).toMatch(/buildAppRouteContributions\(runtimePlugins\)/);
  expect(appSource).toMatch(/runtimePlugins=\{runtimePlugins\}/);
  expect(appSource).not.toMatch(/usePluginRuntime/);
  expect(appSource).not.toMatch(/fetchPlugins/);
});

test("plugin-owned app routes are generated from runtime contributions only", () => {
  expect(appSource).toMatch(/appRouteContributions\.map\(\(route\) => \(/);
  expect(appSource).toMatch(/path=\{route\.path\}/);
  expect(appSource).not.toMatch(/<Route\s+path="\/feedback"/);
  expect(appSource).not.toMatch(/<Route\s+path="\/team"/);
  expect(appSource).not.toMatch(/<Route\s+path="\/agent-team"/);
  expect(appSource).not.toMatch(/<Route\s+path="\/usage"/);
  expect(appSource).not.toMatch(/path:\s*"\/feedback"|path:\s*"\/team"|path:\s*"\/usage"/);
});

test("plugin-owned app routes show a loading route while contributions load", () => {
  expect(appSource).toMatch(/useLocation\(\)/);
  expect(appSource).toMatch(/isLoading:\s*areExtensionContributionsLoading/);
  expect(appSource).toMatch(/CORE_APP_ROUTE_LOADING_PATHS/);
  expect(appSource).toMatch(/isKnownNonPluginPath/);
  expect(appSource).not.toMatch(/"\/team"/);
  expect(appSource).toMatch(/shouldShowPluginRouteLoading/);
  expect(appSource).toMatch(/!isKnownNonPluginPath/);
  expect(appSource).toMatch(/path=\{location\.pathname\}/);
  expect(appSource).toMatch(/<ChatPageSkeleton \/>/);
});

test("extension contribution hook uses the lightweight host endpoint and runtime update event", () => {
  expect(hookSource).toMatch(/pluginRuntimeApi\.listContributions\(\)/);
  expect(hookSource).toMatch(/listenPluginRuntimeUpdated/);
  expect(hookSource).not.toMatch(/pluginRuntimeApi\.list\(\)/);
});
