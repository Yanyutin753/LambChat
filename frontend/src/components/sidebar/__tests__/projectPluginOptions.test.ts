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
  expect(modalSource).toMatch(/pluginRuntimeApi[\s\S]*\.listProjectOptions\(\{ includeInactive: true \}\)/);
  expect(modalSource).not.toMatch(/buildProjectOptionContributions\(/);
  expect(modalSource).toMatch(/projectApi[\s\S]*\.getPluginOptions\(project\.id\)/);
  expect(modalSource).toMatch(/projectApi[\s\S]*\.updatePluginOption\(project\.id, option\.pluginId, option\.key, value\)/);
  expect(modalSource).toMatch(/!option\.effective/);
  expect(modalSource).toMatch(/saved but currently has no effect/);
  expect(modalSource).toMatch(/function hasStoredValue/);
  expect(modalSource).toMatch(/const visibleOptions = options\.filter/);
  expect(modalSource).toMatch(/if \(option\.effective !== false\) return true/);
  expect(modalSource).toMatch(/return hasStoredValue\(values, option\)/);
  expect(modalSource).toMatch(/const fieldDisabled = saving \|\| inactive/);
  expect(modalSource).toMatch(/for \(const option of visibleOptions\)/);
});

test("project menu opens plugin-owned project options", () => {
  expect(menuSource).toMatch(/onPluginOptions/);
  expect(menuSource).toMatch(/SlidersHorizontal/);
  expect(itemSource).toMatch(/onOpenPluginOptions\?: \(project: Project\) => void/);
  expect(itemSource).toMatch(/onPluginOptions=\{/);
  expect(sessionSidebarSource).toMatch(/ProjectPluginOptionsModal/);
  expect(sessionSidebarSource).toMatch(/onOpenProjectPluginOptions: setProjectOptionsProject/);
});

test("agent team project default team uses a controlled renderer", () => {
  expect(rendererSource).toMatch(/"agent_team\.TeamSelectOption"/);
  expect(rendererSource).toMatch(/props\.option\.renderer/);
  expect(rendererSource).toMatch(/if \(!option\.effective\)/);
  expect(rendererSource).toMatch(/placeholder="Team ID"/);
  expect(rendererSource).toMatch(/teamApi[\s\S]*\.list/);
  expect(rendererSource).toMatch(/if \(!option\.effective\) \{[\s\S]*return;[\s\S]*\}/);
});

test("project option renderers do not keep workflow-specific controls", () => {
  expect(rendererSource).not.toMatch(/WorkflowPlugin/);
  expect(rendererSource).not.toMatch(/workflow\.Workflow/);
});
