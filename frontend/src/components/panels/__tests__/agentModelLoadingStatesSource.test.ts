import { readFileSync } from "node:fs";
import { join } from "node:path";

const agentPanelSource = readFileSync(
  join(import.meta.dirname, "../AgentPanel/AgentConfigPanel.tsx"),
  "utf8",
);

const modelPanelSource = readFileSync(
  join(import.meta.dirname, "../ModelPanel/ModelPanel.tsx"),
  "utf8",
);

const agentSectionSource = readFileSync(
  join(import.meta.dirname, "../AgentModelPanel/AgentSection.tsx"),
  "utf8",
);

const modelSectionSource = readFileSync(
  join(import.meta.dirname, "../AgentModelPanel/ModelSection.tsx"),
  "utf8",
);

const tabContentSource = readFileSync(
  join(import.meta.dirname, "../../layout/AppContent/TabContent.tsx"),
  "utf8",
);

test("agent and model configuration pages use matching skeleton screens", () => {
  expect(agentPanelSource).toMatch(/import \{ AgentPanelSkeleton \}/);
  expect(modelPanelSource).toMatch(/import \{ ModelPanelSkeleton \}/);
  expect(agentPanelSource).toMatch(/return <AgentPanelSkeleton \/>/);
  expect(modelPanelSource).toMatch(/return <ModelPanelSkeleton \/>/);
});

test("combined agent model sections use embedded skeleton screens", () => {
  expect(agentSectionSource).toMatch(/import \{ AgentSectionSkeleton \}/);
  expect(modelSectionSource).toMatch(/import \{ ModelSectionSkeleton \}/);
  expect(agentSectionSource).toMatch(/return <AgentSectionSkeleton \/>/);
  expect(modelSectionSource).toMatch(/return <ModelSectionSkeleton \/>/);
  expect(agentSectionSource).not.toMatch(/return <AgentPanelSkeleton \/>/);
  expect(modelSectionSource).not.toMatch(/return <ModelPanelSkeleton \/>/);
});

test("agents tab suspense fallback matches combined configuration panel", () => {
  expect(tabContentSource).toMatch(/AgentModelPanelSkeleton/);
  expect(tabContentSource).toMatch(/agents:\s*<AgentModelPanelSkeleton \/>/);
  expect(tabContentSource).not.toMatch(/agents:\s*<AgentPanelSkeleton \/>/);
});

test("agent and model configuration errors share one callout component", () => {
  for (const source of [
    agentPanelSource,
    modelPanelSource,
    agentSectionSource,
    modelSectionSource,
  ]) {
    expect(source).toMatch(/ConfigPanelErrorCallout/);
  }
});
