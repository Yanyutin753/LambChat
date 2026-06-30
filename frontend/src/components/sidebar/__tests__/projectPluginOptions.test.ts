import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const modalSource = readFileSync(
  new URL("../ProjectPluginOptionsModal.tsx", import.meta.url),
  "utf8",
);
const menuSource = readFileSync(
  new URL("../ProjectMenu.tsx", import.meta.url),
  "utf8",
);
const itemSource = readFileSync(
  new URL("../ProjectItem.tsx", import.meta.url),
  "utf8",
);
const sessionSidebarSource = readFileSync(
  new URL("../../panels/SessionSidebar.tsx", import.meta.url),
  "utf8",
);
const rendererSource = readFileSync(
  new URL("../projectOptionRenderers.tsx", import.meta.url),
  "utf8",
);

test("project plugin options modal is contribution-driven", () => {
  assert.match(modalSource, /pluginRuntimeApi[\s\S]*\.listProjectOptions\(\{ includeInactive: true \}\)/);
  assert.doesNotMatch(modalSource, /buildProjectOptionContributions\(/);
  assert.match(modalSource, /projectApi[\s\S]*\.getPluginOptions\(project\.id\)/);
  assert.match(modalSource, /projectApi[\s\S]*\.updatePluginOption\(project\.id, option\.pluginId, option\.key, value\)/);
  assert.match(modalSource, /!option\.effective/);
  assert.match(modalSource, /saved but currently has no effect/);
  assert.match(modalSource, /function hasStoredValue/);
  assert.match(modalSource, /const visibleOptions = options\.filter/);
  assert.match(modalSource, /if \(option\.effective !== false\) return true/);
  assert.match(modalSource, /return hasStoredValue\(values, option\)/);
  assert.match(modalSource, /const fieldDisabled = saving \|\| inactive/);
  assert.match(modalSource, /const pluginValues =/);
  assert.match(modalSource, /pluginValues,/);
  assert.match(modalSource, /onPluginValueChange/);
  assert.match(modalSource, /for \(const option of visibleOptions\)/);
});

test("project menu opens plugin-owned project options", () => {
  assert.match(menuSource, /onPluginOptions/);
  assert.match(menuSource, /SlidersHorizontal/);
  assert.match(itemSource, /onOpenPluginOptions\?: \(project: Project\) => void/);
  assert.match(itemSource, /onPluginOptions=\{/);
  assert.match(sessionSidebarSource, /ProjectPluginOptionsModal/);
  assert.match(sessionSidebarSource, /onOpenProjectPluginOptions: setProjectOptionsProject/);
});

test("agent team project default team uses a controlled renderer", () => {
  assert.match(rendererSource, /"agent_team\.TeamSelectOption"/);
  assert.match(rendererSource, /props\.option\.renderer/);
  assert.match(rendererSource, /if \(!option\.effective\)/);
  assert.match(rendererSource, /placeholder="Team ID"/);
  assert.match(rendererSource, /teamApi[\s\S]*\.list/);
  assert.match(rendererSource, /if \(!option\.effective\) \{[\s\S]*return;[\s\S]*\}/);
});

test("workflow workflow project and session options use a controlled workflow renderer", () => {
  assert.match(rendererSource, /WorkflowPluginSelectOption/);
  assert.match(rendererSource, /WorkflowPluginVersionSelectOption/);
  assert.match(rendererSource, /"workflow\.WorkflowSelectOption"/);
  assert.match(rendererSource, /"workflow\.WorkflowVersionSelectOption"/);
  assert.match(rendererSource, /inactive=\{!props\.option\.effective\}/);
});
